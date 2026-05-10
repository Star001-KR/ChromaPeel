// Shared mutable state for the chroma + grid modes.
// ESM module objects are singletons, so every importer sees the same
// reference. Crop has its own private state inside crop.js.
export const state = {
  mode: 'chroma',  // 'chroma' | 'grid' | 'crop'
  sourceImageData: null,
  sourceFilename: null,
  processedBlob: null,
  processedURL: null,
  // chroma params
  autoDetect: false,
  targetColor: [255, 37, 255],
  tolerance: 20,
  feather: 100,
  decontaminate: true,
  edgeErosion: 1,
  autoTrim: false,
  trimPadding: 0,
  // grid params
  gridSubMode: 'rowsCols',  // 'rowsCols' | 'cellWH'
  gridRows: 2,
  gridCols: 2,
  gridCellW: 64,
  gridCellH: 64,
  gridResults: [],          // [{name, blob, url, row, col}]
};
