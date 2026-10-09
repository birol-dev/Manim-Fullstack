const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "video[controls]",
  "[tabindex]",
].join(",");

function isRendered(element: HTMLElement): boolean {
  return element.getClientRects().length > 0;
}

/**
 * Move focus to the first tabbable element after *container* in document order
 * (skipping resize handles), like pressing Tab would if the container didn't
 * keep Tab for itself. Returns false when there is nothing after it.
 */
export function focusNextAfter(container: Element, isVisible: (element: HTMLElement) => boolean = isRendered): boolean {
  const candidates = Array.from(document.querySelectorAll<HTMLElement>(FOCUSABLE));
  const next = candidates.find(
    (element) =>
      element.tabIndex >= 0 &&
      !container.contains(element) &&
      Boolean(container.compareDocumentPosition(element) & Node.DOCUMENT_POSITION_FOLLOWING) &&
      element.getAttribute("role") !== "separator" &&
      !element.closest("[inert], [aria-hidden='true']") &&
      isVisible(element),
  );
  if (!next) return false;
  next.focus();
  return true;
}
