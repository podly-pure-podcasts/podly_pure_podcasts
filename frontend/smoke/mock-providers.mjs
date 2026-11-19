// A stand-in for the podcast host, the transcription API and the LLM, so a smoke
// run exercises the whole processing pipeline without keys or network access.
//
//   GET  /feed.xml                   three-episode RSS feed
//   GET  /artwork.svg                feed artwork (Podly requires a channel image)
//   GET  /audio/<n>.mp3              the 66-second sample in src/tests/data, looped to fit the transcript
//   GET  /v1/models                  remote Whisper connection probe
//   POST /v1/audio/transcriptions    the canned transcript below (verbose_json)
//   POST /v1/chat/completions        ad classification and boundary refinement
//
// Usage: node smoke/mock-providers.mjs [port]
import fs from 'fs';
import http from 'http';
import path from 'path';
import { fileURLToPath } from 'url';

const PORT = Number(process.argv[2] || process.env.SMOKE_MOCK_PORT || 5098);
const SAMPLE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../src/tests/data/count_0_99.mp3');

// Podly widens ad breaks by itself: it adds lines within 10 s of an ad, up to
// three intro lines when an ad starts in the first 45 s, merges ads less than
// 60 s apart and runs an ad to the end when less than 60 s follow it. Lines are
// 11 s long and the ads sit mid-episode, well apart, so the cuts match the two
// sponsor reads exactly.
const LINE_SECONDS = 11;
const SCRIPT = [
  ['Welcome to Smoke Signals, a show recorded entirely for automated tests.', false],
  ['Today we follow one episode from the moment Podly finds it in a feed.', false],
  ['The first stop is the download, which saves the original audio as is.', false],
  ['Next the audio is split into chunks small enough for a transcription service.', false],
  ['Each chunk comes back as lines of text with a start and end time.', false],
  ['Those lines are what a language model reads when it looks for sponsors.', false],
  ['It answers with the start times of every line that sounds like an ad.', false],
  ['Before we get into how the cuts are made, a word from our sponsors.', false],
  ['This episode is brought to you by Acme Mattress. Sleep better tonight.', true],
  ['Acme mattresses ship free in a box with a hundred night free trial.', true],
  ['Go to acme.com slash smoke and use code PODLY for fifteen percent off.', true],
  ['That is acme.com slash smoke, promo code PODLY. Now back to the show.', true],
  ['So the model has given us a list of lines it believes are sponsor reads.', false],
  ['Neighbouring lines get a second look, since ads rarely last a single sentence.', false],
  ['Lines that fall close together are merged into one continuous ad break.', false],
  ['The edges of each break can then be nudged to the nearest natural pause.', false],
  ['With the breaks settled, the audio tool removes those stretches of time.', false],
  ['A short fade at each join keeps the edit from sounding like a hard jump.', false],
  ['The finished file replaces the original in the feed your player reads.', false],
  ['Every step is recorded, which is what the statistics window shows you.', false],
  ['You can see each model call, every transcript line and every decision.', false],
  ['One more short break and then we will wrap things up.', false],
  ['Support for this show comes from Example Bank, banking that stays out of your way.', true],
  ['Open an account at examplebank.com today and get your first year free.', true],
  ['Example Bank, member of a made up deposit insurance scheme.', true],
  ['That covers the whole trip from feed to finished episode.', false],
  ['If something looks wrong, the statistics window is the first place to look.', false],
  ['The transcript tab shows exactly what the transcription service heard.', false],
  ['The model calls tab shows what was asked and what came back.', false],
  ['And the identifications tab shows which lines were marked, and how sure it was.', false],
  ['Most problems turn out to be a line that was marked when it should not be.', false],
  ['Those are easy to spot once you know where to look.', false],
  ['Thanks to everyone who helps keep Podly running and improving.', false],
  ['That is all for this episode of Smoke Signals.', false],
  ['Thanks for listening, and see you next week.', false],
];
const TRANSCRIPT = SCRIPT.map(([text, ad], i) => ({ start: i * LINE_SECONDS, end: (i + 1) * LINE_SECONDS, text, ad }));
const AUDIO_SECONDS = TRANSCRIPT.length * LINE_SECONDS;
const SAMPLE_SECONDS = 66;

const EPISODES = [
  { n: 3, title: 'Episode 3: Cutting time', daysAgo: 0 },
  { n: 2, title: 'Episode 2: Timestamps', daysAgo: 7 },
  { n: 1, title: 'Episode 1: Hello, smoke', daysAgo: 14 },
];

// MP3 frames are self-contained, so repeating the sample makes a longer episode
// once its ID3v2 tag (10-byte header plus a syncsafe size) is dropped.
function withoutId3(mp3) {
  if (mp3.toString('latin1', 0, 3) !== 'ID3') return mp3;
  const size = (mp3[6] << 21) | (mp3[7] << 14) | (mp3[8] << 7) | mp3[9];
  return mp3.subarray(10 + size);
}
const AUDIO = Buffer.concat(Array(Math.ceil(AUDIO_SECONDS / SAMPLE_SECONDS)).fill(withoutId3(fs.readFileSync(SAMPLE))));

const xmlEscape = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function feedXml(origin) {
  const size = AUDIO.length;
  const items = EPISODES.map(({ n, title, daysAgo }) => `
    <item>
      <title>${xmlEscape(title)}</title>
      <description>A six minute episode with two sponsor reads.</description>
      <guid isPermaLink="false">smoke-signals-${n}</guid>
      <pubDate>${new Date(Date.now() - daysAgo * 86400000).toUTCString()}</pubDate>
      <enclosure url="${origin}/audio/${n}.mp3" length="${size}" type="audio/mpeg"/>
      <itunes:duration>${AUDIO_SECONDS}</itunes:duration>
    </item>`).join('');
  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Smoke Signals</title>
    <link>${origin}/</link>
    <description>A mock podcast for Podly smoke tests.</description>
    <language>en</language>
    <itunes:author>Podly smoke tests</itunes:author>
    <image><url>${origin}/artwork.svg</url><title>Smoke Signals</title><link>${origin}/</link></image>
    <itunes:image href="${origin}/artwork.svg"/>${items}
  </channel>
</rss>
`;
}

const ARTWORK = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600">
  <rect width="600" height="600" fill="#1f3a5f"/>
  <circle cx="300" cy="250" r="120" fill="none" stroke="#f4b860" stroke-width="28"/>
  <text x="300" y="480" fill="#f4f1ea" font-family="sans-serif" font-size="64" font-weight="700" text-anchor="middle">Smoke Signals</text>
</svg>
`;

function transcription() {
  return {
    task: 'transcribe',
    language: 'english',
    duration: AUDIO_SECONDS,
    text: TRANSCRIPT.map((s) => s.text).join(' '),
    segments: TRANSCRIPT.map((s, id) => ({
      id,
      seek: 0,
      start: s.start,
      end: s.end,
      text: ` ${s.text}`,
      tokens: [],
      temperature: 0,
      avg_logprob: -0.2,
      compression_ratio: 1.3,
      no_speech_prob: 0.01,
    })),
  };
}

// Ad classification prompts list transcript lines as "[<start seconds>] <text>".
// The system prompt carries a worked example in the same format, so only the
// user messages are read.
function classify(userText) {
  const offsets = [...userText.matchAll(/^\[(\d+(?:\.\d+)?)\]/gm)].map((m) => Number(m[1]));
  const ads = offsets.filter((offset) => TRANSCRIPT.some((s) => s.ad && Math.abs(s.start - offset) < 0.5));
  return ads.length
    ? { ad_segments: ads.map((segment_offset) => ({ segment_offset, confidence: 0.95 })), content_type: 'promotional_external', confidence: 0.95 }
    : { ad_segments: [] };
}

function chatReply(messages) {
  const userText = messages
    .filter((m) => m.role === 'user')
    .map((m) => (typeof m.content === 'string' ? m.content : (m.content || []).map((p) => p.text || '').join('\n')))
    .join('\n');
  if (userText.includes('refined_start_phrase')) {
    // Omitting both phrases keeps the detected boundaries.
    return { start_adjustment_reason: 'No adjustment needed', end_adjustment_reason: 'No adjustment needed' };
  }
  const block = userText.match(/Detected Ad Block\**:\s*([\d.]+)s\s*-\s*([\d.]+)s/);
  if (block) {
    return {
      refined_start: Number(block[1]),
      refined_end: Number(block[2]),
      start_adjustment_reason: 'No adjustment needed',
      end_adjustment_reason: 'No adjustment needed',
    };
  }
  return classify(userText);
}

function chatCompletion(body) {
  const content = JSON.stringify(chatReply(body.messages || []));
  const promptTokens = Math.ceil(JSON.stringify(body.messages || []).length / 4);
  const completionTokens = Math.ceil(content.length / 4);
  return {
    id: `chatcmpl-smoke-${Date.now()}`,
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model: body.model || 'smoke-mock',
    choices: [{ index: 0, message: { role: 'assistant', content }, finish_reason: 'stop' }],
    usage: { prompt_tokens: promptTokens, completion_tokens: completionTokens, total_tokens: promptTokens + completionTokens },
  };
}

const readBody = (req) =>
  new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });

const sendJson = (res, status, payload) => {
  res.writeHead(status, { 'content-type': 'application/json' });
  res.end(JSON.stringify(payload));
};

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://mock');
  const route = `${req.method} ${url.pathname.replace(/^\/v1(?=\/)/, '')}`;
  try {
    const body = await readBody(req);
    console.log(`[${new Date().toISOString().slice(11, 19)}] ${req.method} ${url.pathname}`);
    if (route === 'GET /feed.xml') {
      res.writeHead(200, { 'content-type': 'application/rss+xml' });
      res.end(feedXml(`http://${req.headers.host}`));
    } else if (route === 'GET /artwork.svg') {
      res.writeHead(200, { 'content-type': 'image/svg+xml' });
      res.end(ARTWORK);
    } else if (req.method === 'GET' && /^\/audio\/\d+\.mp3$/.test(url.pathname)) {
      res.writeHead(200, { 'content-type': 'audio/mpeg', 'content-length': AUDIO.length });
      res.end(AUDIO);
    } else if (route === 'GET /models') {
      sendJson(res, 200, { object: 'list', data: [{ id: 'whisper-1', object: 'model', owned_by: 'smoke' }] });
    } else if (route === 'POST /audio/transcriptions') {
      sendJson(res, 200, transcription());
    } else if (route === 'POST /chat/completions') {
      sendJson(res, 200, chatCompletion(JSON.parse(body.toString('utf8') || '{}')));
    } else {
      sendJson(res, 404, { error: { message: `no mock for ${route}` } });
    }
  } catch (err) {
    sendJson(res, 500, { error: { message: err.message } });
  }
});

server.listen(PORT, '0.0.0.0', () => console.log(`mock providers on :${PORT}`));
