// Monaco ships no typings for its internal modules; this is the part monacoCore.ts uses.
declare module "monaco-editor-esm/editor/browser/config/tabFocus.js" {
  export const TabFocus: {
    getTabFocusMode(): boolean;
    setTabFocusMode(tabFocusMode: boolean): void;
    onDidChangeTabFocus(listener: (tabFocusMode: boolean) => void): { dispose(): void };
  };
}
