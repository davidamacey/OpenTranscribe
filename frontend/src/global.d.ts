declare global {
  interface Window {
    runTests: () => void;
    testFileDetail: () => void;
  }
}

export {};