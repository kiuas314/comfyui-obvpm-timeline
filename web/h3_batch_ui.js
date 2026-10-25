import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE = "H3BatchPlan";

function widgetValue(node, name) {
    return node.widgets?.find((widget) => widget.name === name)?.value ?? "";
}

function setButton(button, label, disabled = false) {
    button.name = label;
    button.disabled = disabled;
}

app.registerExtension({
    name: "obvpm.h3.batch",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE) return;
        const original = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            original?.apply(this, arguments);
            const node = this;
            const button = node.addWidget(
                "button", "queue remaining", null, async () => {
                    setButton(button, "checking manifest…", true);
                    try {
                        const response = await api.fetchApi(
                            "/obvpm/h3/batch_status", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                    manifest_path: widgetValue(node, "manifest_path"),
                                    batch_id: widgetValue(node, "batch_id"),
                                    base_folder: widgetValue(node, "base_folder"),
                                }),
                            });
                        const status = await response.json();
                        if (!response.ok || status.error) {
                            throw new Error(status.error || `HTTP ${response.status}`);
                        }
                        if (!status.remaining) {
                            const label = status.export_error
                                ? "clips complete; export failed"
                                : `complete ${status.completed}/${status.total}`;
                            setButton(button, label);
                            if (status.export_error) {
                                console.error(
                                    "[obvpm h3] final batch export failed:",
                                    status.export_error);
                            }
                            return;
                        }
                        const noun = status.remaining === 1 ? "clip" : "clips";
                        setButton(
                            button, `queueing ${status.remaining} ${noun}…`,
                            true);
                        // ComfyUI snapshots this graph once per batch item.
                        // H3BatchPlan is deliberately non-cacheable and reads
                        // the checkpoint during execution, so those identical
                        // queued prompts select successive manifest items.
                        const queued = await app.queuePrompt(0, status.remaining);
                        if (queued === false) {
                            throw new Error("ComfyUI did not queue the batch");
                        }
                        setButton(
                            button,
                            `queued ${status.remaining} `
                            + `(${status.completed}/${status.total} done)`);
                    } catch (error) {
                        console.error("[obvpm h3] batch queue failed", error);
                        setButton(button, `queue failed: ${error.message || error}`);
                    } finally {
                        button.disabled = false;
                        node.setDirtyCanvas?.(true, true);
                    }
                });
            // It is a control, not an input. In particular it must not append
            // a positional widgets_values entry to saved workflows.
            button.serialize = false;
            button.options ??= {};
            button.options.serialize = false;
        };
    },
});
