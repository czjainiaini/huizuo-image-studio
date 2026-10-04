import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

async function hostFixture() {
  let extension, sidebar;
  const calls = { create: 0, destroy: 0, refresh: 0, sync: 0 };
  const sourceUrl = new URL("../custom_nodes/ComfyUI-HuizuoPanel/web/studio.js", import.meta.url);
  const source = fs.readFileSync(sourceUrl, "utf8")
    .replace(/^import .*;\r?$/gm, "")
    .replaceAll("import.meta.url", JSON.stringify(sourceUrl.href));
  const app = {
    graph: {}, registerExtension(value) { extension = value; },
    extensionManager: { registerSidebarTab(value) { sidebar = value; } },
  };
  vm.runInNewContext(source, {
    app, api: { apiURL: path => path, addEventListener() {} },
    document: { createElement() { return {}; }, head: { append() {} } },
    createPanel() {
      calls.create++;
      return { destroy() { calls.destroy++; }, refresh() { calls.refresh++; },
        syncFromGraph() { calls.sync++; } };
    },
    URL, URLSearchParams, console, enhanceLocally() {},
  }, { filename: sourceUrl.pathname });
  await extension.setup();
  return { calls, extension, sidebar, container: { dataset: {} } };
}

test("reactive host renders reuse the mounted panel while prompt widgets change", async () => {
  const { calls, sidebar, container } = await hostFixture();
  sidebar.render(container);
  for (let i = 0; i < 12; i++) sidebar.render(container);
  assert.equal(calls.create, 1, "a keystroke must not recreate the editing textarea");
  assert.equal(calls.destroy, 0, "a keystroke must not destroy its focused panel");
  assert.equal(calls.sync, 12, "external graph changes should still synchronize existing controls");
});

test("workflow configuration still refreshes, and a new sidebar container remounts", async () => {
  const { calls, extension, sidebar, container } = await hostFixture();
  sidebar.render(container);
  extension.afterConfigureGraph();
  assert.equal(calls.refresh, 1);
  sidebar.render({ dataset: {} });
  assert.equal(calls.create, 2);
  assert.equal(calls.destroy, 1);
  sidebar.destroy();
  sidebar.render(container);
  assert.equal(calls.create, 3);
  assert.equal(calls.destroy, 2);
});
