export async function copyTextToClipboard(text: string): Promise<void> {
  if (!text) {
    throw new Error('No text to copy');
  }

  // Try modern clipboard API first (works on most browsers including iOS 13.4+)
  // Note: On iOS Safari, this can silently fail even without throwing
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      // Verify it actually worked by reading back (if permitted)
      try {
        const clipboardText = await navigator.clipboard.readText();
        if (clipboardText === text) {
          return; // Confirmed success
        }
      } catch {
        // Can't verify, assume it worked since writeText didn't throw
        return;
      }
    } catch {
      // Fall through to legacy method
    }
  }

  // Legacy fallback - use execCommand which works on older iOS
  const textArea = document.createElement('textarea');
  textArea.value = text;
  
  // Styling to prevent iOS issues
  textArea.style.position = 'fixed';
  textArea.style.top = '0';
  textArea.style.left = '0';
  textArea.style.width = '2em';
  textArea.style.height = '2em';
  textArea.style.padding = '0';
  textArea.style.border = 'none';
  textArea.style.outline = 'none';
  textArea.style.boxShadow = 'none';
  textArea.style.background = 'transparent';
  textArea.style.fontSize = '16px'; // Prevent iOS zoom
  
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  
  // iOS needs setSelectionRange
  try {
    textArea.setSelectionRange(0, text.length);
  } catch {
    // Ignore if not supported
  }

  let successful = false;
  try {
    successful = document.execCommand('copy');
  } catch {
    successful = false;
  }
  
  document.body.removeChild(textArea);

  if (!successful) {
    throw new Error('Copy failed - please copy manually');
  }
}
