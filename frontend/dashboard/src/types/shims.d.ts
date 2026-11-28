/// <reference types="vite/client" />

declare module "cytoscape-dagre" {
  import type cytoscape from "cytoscape";
  const plugin: cytoscape.Ext;
  export default plugin;
}
