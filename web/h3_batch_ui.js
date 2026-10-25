import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE = "H3BatchPlan";
const ROOT_BLOCKS = ["project", "characters", "locations", "audio", "defaults"];
const CLIP_FIELDS = [
    ["context", "Context", "json", "'none', 'previous', an earlier clip id, or a context object"],
    ["duration_seconds", "Duration (seconds)", "number", "Optional; otherwise defaults.duration_seconds or 8"],
    ["seed", "Seed", "number", "Optional fixed generation seed"],
    ["filename_prefix", "Filename prefix", "text", "Optional output filename stem"],
    ["negative_prompt", "Negative prompt", "long", "Overrides the project negative prompt"],
    ["raw_prompt", "Raw H3 prompt", "long", "Bypasses structured prompt compilation"],
    ["prompt", "Legacy prompt", "long", "Required only for version 1 manifests"],
    ["cast", "Cast", "json", "JSON array of character ids"],
    ["location", "Location", "json", "Location id or inline location object"],
    ["music", "Music", "json", "Preset id, inline description, false, or 'none'"],
    ["soundscape", "Soundscape", "json", "Inline ambience, false, or 'none'"],
    ["camera", "Camera", "json", "movement / amplitude / speed / target"],
    ["continuity", "Continuity", "json", "Text or inherit_motion / inherit_action / notes object"],
    ["shot", "Single shot", "json", "framing / action / camera / dialogue"],
    ["shots", "Multi-shot sequence", "json", "Array of timestamped shot blocks"],
    ["dialogue", "Dialogue", "json", "Array of dialogue blocks for a single-shot clip"],
    ["character_overrides", "Character overrides", "json", "Per-clip appearance or wardrobe changes"],
    ["window", "Context window", "text", "5, 22, 39, or 56"],
    ["mode", "Pin mode", "text", "masked, guide, or both"],
    ["metadata", "Metadata", "json", "Extra JSON object stored with the take"],
];

function widget(node, name) {
    return node.widgets?.find((one) => one.name === name);
}

function widgetValue(node, name) {
    return widget(node, name)?.value ?? "";
}

function setWidgetValue(node, name, value) {
    const found = widget(node, name);
    if (!found) return;
    found.value = value;
    const element = found.element ?? found.inputEl;
    if (element) element.value = value;
    found.callback?.(value);
    node.setDirtyCanvas?.(true, true);
}

function inputValue(node, name) {
    const index = node.inputs?.findIndex((input) => input.name === name) ?? -1;
    if (index >= 0 && node.inputs[index]?.link != null) {
        try {
            const source = node.getInputNode?.(index);
            if (source) {
                const exact = widgetValue(source, name);
                if (exact !== "") return exact;
                return source.widgets?.[0]?.value ?? "";
            }
        } catch (error) {
            console.debug("[obvpm h3] could not read linked batch input", error);
        }
    }
    return widgetValue(node, name);
}

async function post(path, body) {
    const response = await api.fetchApi(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok || result.error) {
        throw new Error(result.error || `HTTP ${response.status}`);
    }
    return result;
}

function installStyle() {
    if (document.getElementById("h3-batch-editor-style")) return;
    const style = document.createElement("style");
    style.id = "h3-batch-editor-style";
    style.textContent = `
      .h3be{height:1880px;box-sizing:border-box;display:flex;flex-direction:column;gap:9px;
        padding:10px;color:#e8eaee;background:#171a20;font:13px/1.35 system-ui,sans-serif;overflow:hidden}
      .h3be *{box-sizing:border-box}.h3be button,.h3be input,.h3be select,.h3be textarea{font:inherit}
      .h3be button{background:#2b313b;color:#eef1f5;border:1px solid #46505d;border-radius:5px;
        padding:6px 10px;cursor:pointer}.h3be button:hover{background:#384352}.h3be button:disabled{opacity:.5;cursor:default}
      .h3be .primary{background:#286b87;border-color:#3b91b3}.h3be .danger{color:#ffb0aa}
      .h3be-toolbar,.h3be-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap}
      .h3be-status{margin-left:auto;color:#a9b2bf;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:48%}
      .h3be-body{min-height:0;flex:1;display:grid;grid-template-columns:265px minmax(0,1fr);gap:10px}
      .h3be-sidebar,.h3be-main{min-height:0;border:1px solid #343b46;border-radius:7px;background:#20242b;overflow:hidden}
      .h3be-sidebar{display:flex;flex-direction:column}.h3be-sidehead{padding:9px;border-bottom:1px solid #343b46;display:flex;gap:6px}
      .h3be-clips{overflow:auto;padding:7px;display:flex;flex-direction:column;gap:5px}.h3be-segment{font-size:11px;color:#7ec8e3;margin:8px 4px 2px}
      .h3be-clip{display:flex;gap:6px;align-items:center;text-align:left;width:100%;padding:8px}.h3be-clip.on{background:#2d6072;border-color:#55a6c4}
      .h3be-clip small{color:#aab3bf;margin-left:auto}.h3be-main{display:flex;flex-direction:column}
      .h3be-tabs{display:flex;gap:5px;padding:8px;border-bottom:1px solid #343b46}.h3be-tabs button.on{background:#2d6072;border-color:#55a6c4}
      .h3be-pane{min-height:0;flex:1;overflow:auto;padding:12px}.h3be-fields{display:grid;grid-template-columns:1fr 1fr;gap:9px}
      .h3be-field{border:1px solid #363e49;border-radius:6px;padding:8px;background:#252a32}.h3be-field.wide{grid-column:1/-1}
      .h3be-field label{display:flex;gap:7px;align-items:center;font-weight:650;margin-bottom:5px}.h3be-field p{margin:0 0 6px;color:#8f99a6;font-size:11px}
      .h3be input[type=text],.h3be input[type=number],.h3be select,.h3be textarea{width:100%;background:#15181d;color:#f0f2f4;border:1px solid #414a57;border-radius:4px;padding:6px}
      .h3be textarea{resize:vertical;min-height:74px;font:12px/1.4 ui-monospace,SFMono-Regular,monospace}.h3be textarea.long{min-height:125px}
      .h3be h3{margin:0 0 9px;font-size:16px}.h3be h4{margin:14px 0 7px;color:#9fdcf2}.h3be-note{color:#9ca7b4;font-size:12px}
      .h3be-prompt{white-space:pre-wrap;overflow:auto;max-height:430px;min-height:150px;padding:10px;border-radius:6px;background:#111419;border:1px solid #39414d;color:#d9eef7;font:12px/1.45 ui-monospace,SFMono-Regular,monospace}
      .h3be-jsonbad{border-color:#c65b55!important}.h3be-raw{margin-top:9px;min-height:500px}
      .h3be-global{margin-bottom:10px}.h3be-global textarea{min-height:150px}.h3be-spacer{flex:1}
    `;
    document.head.appendChild(style);
}

function el(tag, className, text) {
    const found = document.createElement(tag);
    if (className) found.className = className;
    if (text !== undefined) found.textContent = text;
    return found;
}

function button(label, title, action, className = "") {
    const found = el("button", className, label);
    found.type = "button";
    found.title = title || "";
    found.addEventListener("click", action);
    return found;
}

function parseFlexible(text) {
    const value = String(text).trim();
    if (!value) return "";
    try { return JSON.parse(value); } catch (_) { return value; }
}

function freshClip(index) {
    return {
        id: `clip_${index + 1}`,
        context: index ? "previous" : "none",
        duration_seconds: 8,
        shot: { action: "Describe the action in this clip." },
    };
}

function buildEditor(node) {
    installStyle();
    const manifestWidget = widget(node, "manifest_yaml");
    const selectionWidget = widget(node, "run_selection");
    for (const found of [manifestWidget, selectionWidget]) {
        if (!found) continue;
        found.hidden = true;
        (found.options ??= {}).hidden = true;
        const element = found.element ?? found.inputEl;
        if (element) element.style.display = "none";
    }

    const root = el("div", "h3be");
    root.addEventListener("pointerdown", (event) => event.stopPropagation());
    root.addEventListener("wheel", (event) => event.stopPropagation());
    const toolbar = el("div", "h3be-toolbar");
    const body = el("div", "h3be-body");
    const sidebar = el("div", "h3be-sidebar");
    const main = el("div", "h3be-main");
    const status = el("span", "h3be-status", "loading manifest…");
    const file = el("input");
    file.type = "file";
    file.accept = ".yaml,.yml,.json,text/yaml,application/json";
    file.style.display = "none";
    root.append(toolbar, body, file);
    body.append(sidebar, main);

    let documentModel = null;
    let inspection = null;
    let selectedIndex = 0;
    let tab = "clip";
    let syncTimer = null;
    let syncPromise = Promise.resolve();
    let revision = 0;

    function setStatus(text, error = false) {
        status.textContent = text;
        status.style.color = error ? "#ff9d95" : "#a9b2bf";
    }

    async function inspectYaml(text, replaceWidget = true) {
        const serial = ++revision;
        setStatus("validating and compiling…");
        const found = await post("/obvpm/h3/batch_inspect", { manifest_yaml: text });
        if (serial !== revision) return found;
        documentModel = found.document;
        inspection = found;
        if (replaceWidget) setWidgetValue(node, "manifest_yaml", text);
        selectedIndex = Math.min(selectedIndex,
            Math.max(0, (documentModel.clips?.length ?? 1) - 1));
        setStatus(`${found.clips.length} clips · ${found.segments.length} segments · valid`);
        render();
        return found;
    }

    async function serialize(renderAfter = false) {
        if (!documentModel) return null;
        const serial = ++revision;
        setStatus("saving YAML and compiling prompts…");
        const found = await post("/obvpm/h3/batch_serialize", { document: documentModel });
        if (serial !== revision) return found;
        inspection = found;
        setWidgetValue(node, "manifest_yaml", found.manifest_yaml);
        setStatus(`${found.clips.length} clips · ${found.segments.length} segments · saved`);
        if (renderAfter) {
            documentModel = found.document;
            render();
        } else {
            // Keep the current object identity: live form controls close over
            // its clip objects. Replacing it here would make every control
            // stale after its first successful autosave.
            renderSidebar();
            refreshPrompt();
        }
        return found;
    }

    function scheduleSerialize() {
        clearTimeout(syncTimer);
        syncTimer = setTimeout(() => {
            syncPromise = serialize(false).catch((error) => {
                setStatus(error.message || String(error), true);
            });
        }, 450);
    }

    async function flush() {
        clearTimeout(syncTimer);
        syncPromise = serialize(false);
        return syncPromise;
    }

    function selectedClip() {
        return documentModel?.clips?.[selectedIndex] ?? null;
    }

    function compiledClip() {
        const id = selectedClip()?.id;
        return inspection?.clips?.find((clip) => clip.id === id) ?? null;
    }

    function refreshPrompt() {
        const prompt = root.querySelector(".h3be-prompt");
        const compiled = compiledClip();
        if (prompt) prompt.textContent = compiled?.compiled_prompt
            ?? "Fix validation errors to see the generated H3 prompt.";
        const negative = root.querySelector("[data-negative]");
        if (negative) negative.textContent = compiled?.negative_prompt
            ? `Negative: ${compiled.negative_prompt}` : "Negative: (empty)";
    }

    function fieldControl(clip, key, label, kind, help) {
        const wide = kind === "json" || kind === "long";
        const wrap = el("div", "h3be-field" + (wide ? " wide" : ""));
        const heading = el("label");
        const enabled = el("input");
        enabled.type = "checkbox";
        enabled.checked = Object.prototype.hasOwnProperty.call(clip, key);
        heading.append(enabled, document.createTextNode(label));
        wrap.append(heading, el("p", "", help));
        let control;
        const value = clip[key];
        if (kind === "long" || kind === "json") {
            control = el("textarea", kind === "long" ? "long" : "");
            control.value = kind === "json"
                ? (value === undefined ? "" : JSON.stringify(value, null, 2))
                : String(value ?? "");
        } else {
            control = el("input");
            control.type = kind === "number" ? "number" : "text";
            if (kind === "number") control.step = "any";
            control.value = value ?? "";
        }
        control.disabled = !enabled.checked;
        enabled.addEventListener("change", () => {
            if (enabled.checked) {
                if (kind === "number") clip[key] = 0;
                else if (kind === "json") clip[key] = ["cast", "shots", "dialogue"].includes(key) ? [] : {};
                else clip[key] = "";
            } else delete clip[key];
            renderClipPane();
            scheduleSerialize();
        });
        control.addEventListener("input", () => {
            if (!enabled.checked) return;
            if (kind === "number") clip[key] = Number(control.value);
            else if (kind === "json") clip[key] = parseFlexible(control.value);
            else clip[key] = control.value;
            control.classList.remove("h3be-jsonbad");
            scheduleSerialize();
        });
        wrap.append(control);
        return wrap;
    }

    function renderGlobals(pane) {
        pane.append(el("h3", "", "Story globals and reusable libraries"));
        pane.append(el("div", "h3be-note",
            "These blocks are stored in YAML. Edit valid JSON here; export converts it back to readable YAML."));
        const versionWrap = el("div", "h3be-field h3be-global");
        versionWrap.append(el("label", "", "Manifest version"));
        const version = el("select");
        for (const number of [1, 2]) {
            const option = el("option", "", String(number));
            option.value = String(number);
            option.selected = Number(documentModel.version ?? 2) === number;
            version.append(option);
        }
        version.addEventListener("change", () => {
            documentModel.version = Number(version.value);
            scheduleSerialize();
        });
        versionWrap.append(version);
        pane.append(versionWrap);
        for (const key of ROOT_BLOCKS) {
            const wrap = el("div", "h3be-field h3be-global");
            const heading = el("label");
            const enabled = el("input");
            enabled.type = "checkbox";
            enabled.checked = Object.prototype.hasOwnProperty.call(documentModel, key);
            heading.append(enabled, document.createTextNode(key));
            const area = el("textarea");
            area.value = enabled.checked ? JSON.stringify(documentModel[key], null, 2) : "{}";
            area.disabled = !enabled.checked;
            enabled.addEventListener("change", () => {
                if (enabled.checked) documentModel[key] = {};
                else delete documentModel[key];
                render();
                scheduleSerialize();
            });
            area.addEventListener("input", () => {
                try {
                    documentModel[key] = JSON.parse(area.value || "{}");
                    area.classList.remove("h3be-jsonbad");
                    scheduleSerialize();
                } catch (error) {
                    area.classList.add("h3be-jsonbad");
                    setStatus(`${key}: ${error.message}`, true);
                }
            });
            wrap.append(heading, area);
            pane.append(wrap);
        }
    }

    function renderRaw(pane) {
        pane.append(el("h3", "", "Raw YAML"));
        pane.append(el("div", "h3be-note",
            "Use this for advanced edits or pasting a complete manifest. Apply validates it and rebuilds the visual editor."));
        const area = el("textarea", "h3be-raw");
        area.value = String(widgetValue(node, "manifest_yaml"));
        const apply = button("apply YAML", "Validate and load this YAML", async () => {
            try { await inspectYaml(area.value, true); }
            catch (error) { setStatus(error.message || String(error), true); }
        }, "primary");
        pane.append(area, apply);
    }

    function renderClipPane() {
        const pane = main.querySelector(".h3be-pane");
        if (!pane || tab !== "clip") return;
        pane.replaceChildren();
        const clip = selectedClip();
        if (!clip) {
            pane.append(el("h3", "", "No clips"));
            return;
        }
        const titleRow = el("div", "h3be-actions");
        titleRow.append(el("h3", "", `Clip ${selectedIndex + 1}`), el("span", "h3be-spacer"));
        titleRow.append(
            button("↑", "Move clip earlier", () => moveClip(-1)),
            button("↓", "Move clip later", () => moveClip(1)),
            button("duplicate", "Duplicate this clip", duplicateClip),
            button("delete", "Delete this clip", deleteClip, "danger"));
        const idWrap = el("div", "h3be-field");
        idWrap.append(el("label", "", "Clip id (required)"));
        const id = el("input");
        id.type = "text";
        id.value = clip.id ?? "";
        id.addEventListener("input", () => {
            clip.id = id.value;
            scheduleSerialize();
            renderSidebar();
        });
        idWrap.append(id);
        const fields = el("div", "h3be-fields");
        fields.append(idWrap);
        for (const definition of CLIP_FIELDS) fields.append(fieldControl(clip, ...definition));
        const actions = el("div", "h3be-actions");
        actions.append(
            button("generate this clip", "Queue only the selected clip", () => generate("clip"), "primary"),
            button("generate this segment", "Queue this root shot and its continuations", () => generate("segment"), "primary"),
            button("generate whole movie", "Queue every unfinished clip", () => generate("movie"), "primary"));
        const negative = el("div", "h3be-note");
        negative.dataset.negative = "1";
        const prompt = el("pre", "h3be-prompt");
        pane.append(titleRow, actions, fields, el("h4", "", "Compiled H3 prompt"), negative, prompt);
        refreshPrompt();
    }

    function renderSidebar() {
        const list = sidebar.querySelector(".h3be-clips");
        if (!list || !documentModel) return;
        list.replaceChildren();
        const segmentStarts = new Map(
            (inspection?.segments ?? []).map((segment, index) => [segment.clips[0], index + 1]));
        (documentModel.clips ?? []).forEach((clip, index) => {
            if (segmentStarts.has(clip.id)) {
                list.append(el("div", "h3be-segment",
                    `SEGMENT ${segmentStarts.get(clip.id)} · ROOT ${clip.id}`));
            }
            const row = button(clip.id || `(clip ${index + 1})`, "Edit this clip", () => {
                selectedIndex = index;
                tab = "clip";
                render();
            }, "h3be-clip" + (index === selectedIndex ? " on" : ""));
            const info = inspection?.clips?.find((one) => one.id === clip.id);
            row.append(el("small", "", info ? `${info.duration_seconds}s` : "invalid"));
            list.append(row);
        });
    }

    function renderMain() {
        main.replaceChildren();
        const tabs = el("div", "h3be-tabs");
        for (const [key, label] of [["clip", "Clip editor"], ["globals", "Story globals"], ["raw", "Raw YAML"]]) {
            tabs.append(button(label, "", () => { tab = key; renderMain(); }, tab === key ? "on" : ""));
        }
        const pane = el("div", "h3be-pane");
        main.append(tabs, pane);
        if (tab === "globals") renderGlobals(pane);
        else if (tab === "raw") renderRaw(pane);
        else renderClipPane();
    }

    function render() {
        if (!documentModel) return;
        sidebar.replaceChildren();
        const sideHead = el("div", "h3be-sidehead");
        sideHead.append(button("+ clip", "Add a clip", addClip),
                        button("validate", "Validate and recompile all prompts", async () => {
                            try { await flush(); render(); }
                            catch (error) { setStatus(error.message || String(error), true); }
                        }));
        sidebar.append(sideHead, el("div", "h3be-clips"));
        renderSidebar();
        renderMain();
    }

    function addClip() {
        documentModel.clips ??= [];
        documentModel.clips.push(freshClip(documentModel.clips.length));
        selectedIndex = documentModel.clips.length - 1;
        serialize(true).catch((error) => setStatus(error.message || String(error), true));
    }

    function duplicateClip() {
        const source = selectedClip();
        if (!source) return;
        const copy = JSON.parse(JSON.stringify(source));
        copy.id = `${copy.id || "clip"}_copy`;
        documentModel.clips.splice(selectedIndex + 1, 0, copy);
        selectedIndex += 1;
        serialize(true).catch((error) => setStatus(error.message || String(error), true));
    }

    function deleteClip() {
        if (!selectedClip() || !window.confirm(`Delete clip ${selectedClip().id}?`)) return;
        documentModel.clips.splice(selectedIndex, 1);
        selectedIndex = Math.max(0, Math.min(selectedIndex, documentModel.clips.length - 1));
        serialize(true).catch((error) => setStatus(error.message || String(error), true));
    }

    function moveClip(delta) {
        const target = selectedIndex + delta;
        if (target < 0 || target >= documentModel.clips.length) return;
        const [clip] = documentModel.clips.splice(selectedIndex, 1);
        documentModel.clips.splice(target, 0, clip);
        selectedIndex = target;
        serialize(true).catch((error) => setStatus(error.message || String(error), true));
    }

    async function generate(scope) {
        try {
            await flush();
            const clip = compiledClip();
            if (!clip) throw new Error("Selected clip is not valid yet");
            let ids;
            if (scope === "clip") ids = [clip.id];
            else if (scope === "segment") {
                ids = inspection.segments.find((segment) => segment.id === clip.segment)?.clips;
            } else ids = inspection.clips.map((one) => one.id);
            setWidgetValue(node, "run_selection", JSON.stringify(ids));
            setStatus(`checking ${scope} scope…`);
            const found = await post("/obvpm/h3/batch_status", {
                manifest_yaml: widgetValue(node, "manifest_yaml"),
                batch_id: widgetValue(node, "batch_id"),
                base_folder: inputValue(node, "base_folder"),
                run_selection: ids,
            });
            if (!found.remaining) {
                setStatus(`${scope} already complete (${found.completed}/${found.total}); use a new batch_id to regenerate`);
                return;
            }
            setStatus(`queueing ${found.remaining} ${found.remaining === 1 ? "clip" : "clips"}…`);
            const queued = await app.queuePrompt(0, found.remaining);
            if (queued === false) throw new Error("ComfyUI did not queue the selection");
            setStatus(`queued ${found.remaining} · results will be added to Timeline`);
        } catch (error) {
            console.error("[obvpm h3] scoped generation failed", error);
            setStatus(error.message || String(error), true);
        }
    }

    async function exportYaml() {
        try {
            const found = await flush();
            const blob = new Blob([found.manifest_yaml], { type: "text/yaml" });
            const url = URL.createObjectURL(blob);
            const link = el("a");
            const title = documentModel.project?.title || "h3-story";
            link.download = `${String(title).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "h3-story"}.yaml`;
            link.href = url;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            setStatus(`exported ${link.download}`);
        } catch (error) {
            setStatus(error.message || String(error), true);
        }
    }

    file.addEventListener("change", async () => {
        const picked = file.files?.[0];
        if (!picked) return;
        try { await inspectYaml(await picked.text(), true); }
        catch (error) { setStatus(error.message || String(error), true); }
        finally { file.value = ""; }
    });

    toolbar.append(
        button("import YAML", "Load a YAML/JSON screenplay", () => file.click()),
        button("export YAML", "Download the current screenplay", exportYaml),
        button("story globals", "Edit project, characters, locations, audio, and defaults", () => { tab = "globals"; renderMain(); }),
        button("raw YAML", "Advanced source editor", () => { tab = "raw"; renderMain(); }),
        status);

    const domWidget = node.addDOMWidget("h3_story_editor", "div", root,
        { hideOnZoom: false });
    domWidget.serialize = false;
    domWidget.options.serialize = false;
    domWidget.computeLayoutSize = () => ({ minHeight: 1880, minWidth: 900 });
    Object.defineProperty(domWidget, "width", {
        configurable: true, get: () => undefined, set: () => {},
    });

    inspectYaml(String(widgetValue(node, "manifest_yaml")), false)
        .catch((error) => setStatus(error.message || String(error), true));

    // Saved widget values are applied after onNodeCreated. Re-read once the
    // graph has configured the node, otherwise a restored workflow briefly
    // builds the default castle story and never notices its saved YAML.
    const onConfigure = node.onConfigure;
    node.onConfigure = function () {
        const result = onConfigure?.apply(this, arguments);
        setTimeout(() => {
            inspectYaml(String(widgetValue(node, "manifest_yaml")), false)
                .catch((error) => setStatus(error.message || String(error), true));
        }, 0);
        return result;
    };
}

app.registerExtension({
    name: "obvpm.h3.batch.editor",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE) return;
        const original = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = original?.apply(this, arguments);
            try { buildEditor(this); }
            catch (error) { console.error("[obvpm h3] story editor failed", error); }
            return result;
        };
    },
});
