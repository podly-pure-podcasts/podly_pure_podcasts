#!/usr/bin/env bash
# Posts or updates the smoke-test comment on a pull request, from the
# smoke-report artifact of a "Smoke Test" run. Run by smoke-report.yml.
#
# Everything in REPORT_DIR came from a run of pull request code and is
# untrusted: only known file names of the expected type and size are used,
# and only numbers are taken from text files.
#
# Media is hosted on the smoke-media release: a GIF and screenshots show
# inline and the videos are linked. GitHub refuses inline video uploads
# (gh pr comment --attach) from GITHUB_TOKEN.
#
# Env: GH_TOKEN, GH_REPO, REPORT_DIR, RUN_ID, RUN_URL, HEAD_SHA, CONCLUSION,
#      STARTED_AT, UPDATED_AT
set -euo pipefail

MARKER='<!-- podly-smoke-test -->'
RELEASE_TAG=smoke-media
MAX_BYTES=$((10 * 1024 * 1024))

pr=$(head -c 16 "$REPORT_DIR/pr-number" 2>/dev/null | tr -d '[:space:]' || true)
if ! [[ "$pr" =~ ^[0-9]{1,7}$ ]]; then
  echo "No valid PR number in the report; nothing to post."
  exit 0
fi

# The PR number is only a claim; the PR's current head must be the commit
# that was tested.
pr_head=$(gh api "repos/$GH_REPO/pulls/$pr" --jq .head.sha)
if [ "$pr_head" != "$HEAD_SHA" ]; then
  echo "PR #$pr head is $pr_head, but the run tested $HEAD_SHA; not posting."
  exit 0
fi

media=$(mktemp -d)
accept() { # name, mime type
  local src="$REPORT_DIR/$1"
  [ -f "$src" ] && [ ! -L "$src" ] || return 1
  [ "$(file --brief --mime-type "$src")" = "$2" ] || { echo "Skipping $1: not $2"; return 1; }
  [ "$(stat -c %s "$src")" -le "$MAX_BYTES" ] || { echo "Skipping $1: over 10 MB"; return 1; }
  cp "$src" "$media/$1"
}
videos=()
for v in walkthrough.webm enable-and-process.webm; do
  accept "$v" video/webm && videos+=("$v")
done
shots=()
for s in walkthrough-failure.jpg enable-failure.jpg phone-failure.jpg \
  feed.jpg stats-overview.jpg stats-model-calls.jpg settings.jpg enable-confirm.jpg phone.jpg \
  bleeps.jpg audio-segments.jpg; do
  accept "$s" image/jpeg && shots+=("$s")
done
gif=
accept walkthrough.gif image/gif && gif=walkthrough.gif

fmt() { printf '%d:%02d' $(($1 / 60)) $(($1 % 60)); }
# Both processed episodes are cut the same way, so repeated ranges are listed once.
cuts=$(grep -oE '\(([0-9]{1,6})\.[0-9]+, ([0-9]{1,6})\.[0-9]+\)' "$REPORT_DIR/cuts.txt" 2>/dev/null | awk '!seen[$0]++' | head -6 |
  sed -E 's/\(([0-9]+)\.[0-9]+, ([0-9]+)\.[0-9]+\)/\1 \2/' |
  while read -r a b; do printf '%s–%s, ' "$(fmt "$a")" "$(fmt "$b")"; done || true)
cuts=${cuts%, }

elapsed=$(($(date -d "$UPDATED_AT" +%s) - $(date -d "$STARTED_AT" +%s)))
case "$CONCLUSION" in
  success) status="✅ **Smoke test passed**" ;;
  failure) status="❌ **Smoke test failed**" ;;
  *) status="⚠️ **Smoke test $CONCLUSION**" ;;
esac

caption() {
  case "$1" in
    walkthrough-failure.jpg) echo "Walkthrough failure" ;;
    enable-failure.jpg) echo "Enable failure" ;;
    phone-failure.jpg) echo "Phone failure" ;;
    feed.jpg) echo "Processed episode" ;;
    stats-overview.jpg) echo "Stats" ;;
    stats-model-calls.jpg) echo "Model calls" ;;
    settings.jpg) echo "Settings" ;;
    enable-confirm.jpg) echo "Enable episode" ;;
    phone.jpg) echo "Phone" ;;
    bleeps.jpg) echo "Bleeps" ;;
    audio-segments.jpg) echo "INA audio segments" ;;
  esac
}

write_body() {
  {
    echo "$MARKER"
    echo "$status in $(fmt "$elapsed") · [run]($RUN_URL) · \`${HEAD_SHA:0:7}\`"
    echo
    if [ -n "$cuts" ]; then
      echo "Ad breaks cut: $cuts (expected 1:28–2:12, 4:02–4:35)"
      echo
    fi
    for v in "${videos[@]}"; do
      echo "**${v%.webm}**"
      echo
      video_block "$v"
      echo
    done
    if [ ${#shots[@]} -gt 0 ]; then
      local i=0 row_titles="" row_images=""
      echo "| | |"
      echo "|---|---|"
      for s in "${shots[@]}"; do
        row_titles+="| $(caption "$s") "
        row_images+="| $(shot_img "$s" thumb) "
        i=$((i + 1))
        if [ $((i % 2)) -eq 0 ]; then
          echo "$row_titles|"
          echo "$row_images|"
          row_titles="" row_images=""
        fi
      done
      if [ -n "$row_titles" ]; then
        echo "$row_titles| |"
        echo "$row_images| |"
      fi
      echo
      # Release files download when clicked, so full-size copies are inline.
      echo "<details><summary>Full-size screenshots</summary>"
      echo
      for s in "${shots[@]}"; do
        echo "**$(caption "$s")**"
        echo
        shot_img "$s" full
        echo
      done
      echo "</details>"
      echo
    fi
    echo "<sub>Mock providers. The images and videos here are deleted when this PR is merged or closed; the run's \`smoke-output\` artifact keeps every screenshot, video and log for 7 days.</sub>"
  } > "$media/body.md"
}

gh release view "$RELEASE_TAG" > /dev/null 2>&1 ||
  gh release create "$RELEASE_TAG" --prerelease --title "Smoke test media" \
    --notes "Screenshots and recordings for smoke-test comments on pull requests. Managed by smoke-report.yml."
release_id=$(gh api "repos/$GH_REPO/releases/tags/$RELEASE_TAG" --jq .id)
gh api --paginate "repos/$GH_REPO/releases/$release_id/assets" --jq ".[] | select(.name | startswith(\"pr$pr-\")) | .id" |
  while read -r id; do gh api -X DELETE "repos/$GH_REPO/releases/assets/$id"; done

prefix="pr$pr-$RUN_ID-"
upload=()
for f in "${videos[@]}" "${shots[@]}" $gif; do
  cp "$media/$f" "$media/$prefix$f"
  upload+=("$media/$prefix$f")
done
[ ${#upload[@]} -eq 0 ] || gh release upload "$RELEASE_TAG" "${upload[@]}" --clobber

asset_url() { echo "https://github.com/$GH_REPO/releases/download/$RELEASE_TAG/$prefix$1"; }
# shot_img NAME thumb|full. Portrait phone screenshots are sized by height so
# they don't stretch their row.
shot_img() {
  local size
  case "$1:$2" in
    phone*:thumb) size='height="300"' ;;
    phone*:full) size='width="390"' ;;
    *:thumb) size='width="380"' ;;
    *) size='width="100%"' ;;
  esac
  echo "<img src=\"$(asset_url "$1")\" alt=\"$(caption "$1")\" $size>"
}
video_block() {
  if [ "$1" = walkthrough.webm ] && [ -n "$gif" ]; then
    echo "![Walkthrough at 4× speed]($(asset_url "$gif"))"
    echo
  fi
  echo "[Download $1]($(asset_url "$1"))"
}
write_body

comment_id=$(gh api --paginate "repos/$GH_REPO/issues/$pr/comments" \
  --jq ".[] | select(.user.login == \"github-actions[bot]\" and (.body | startswith(\"$MARKER\"))) | .id" | tail -1)
if [ -n "$comment_id" ]; then
  gh api -X PATCH "repos/$GH_REPO/issues/comments/$comment_id" -F "body=@$media/body.md" > /dev/null
else
  gh api -X POST "repos/$GH_REPO/issues/$pr/comments" -F "body=@$media/body.md" > /dev/null
fi
