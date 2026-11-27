/// <reference types="vite/client" />

// TypeScript 7 checks side-effect imports. Vite serves CSS through its asset
// pipeline, so declare stylesheet modules explicitly for the compiler.
declare module '*.css' {}
