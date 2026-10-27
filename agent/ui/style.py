"""Theme and CSS of the web UI."""
import gradio as gr

THEME = gr.themes.Soft(
    primary_hue="indigo",
    neutral_hue="slate",
    font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
)

# One slim scrollbar inside the chat, no extra scroll on the wrapper.
CSS = """
#chat { overflow: hidden; }
#chat * { scrollbar-width: thin; scrollbar-color: var(--border-color-primary) transparent; }
#chat ::-webkit-scrollbar { width: 6px; }
#chat ::-webkit-scrollbar-thumb { background: var(--border-color-primary); border-radius: 3px; }
#chat ::-webkit-scrollbar-button { display: none; }
"""
# Shimmer on the title of a running "thought" block (the spinner is Gradio's own).
CSS += """
@keyframes thinking-shimmer { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }
#chat .thought-group .title:has(.loading-spinner) .md p {
  background: linear-gradient(90deg, var(--body-text-color-subdued) 35%, var(--body-text-color) 50%, var(--body-text-color-subdued) 65%);
  background-size: 200% 100%;
  -webkit-background-clip: text; background-clip: text; color: transparent;
  animation: thinking-shimmer 1.6s linear infinite;
}
"""
# Header, status pills, step tracker, cards.
CSS += """
.hero { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; padding: 4px 2px 6px; }
.hero .brand { display: flex; gap: 14px; align-items: flex-start; max-width: 780px; }
.hero .logo { flex: none; width: 40px; height: 40px; border-radius: 10px; display: grid; place-items: center;
  color: #fff; font-size: 20px; background: linear-gradient(135deg, #6366f1, #8b5cf6); }
.hero h1 { margin: 0; font-size: 22px; font-weight: 650; letter-spacing: -0.01em; }
.hero p { margin: 4px 0 0; color: var(--body-text-color-subdued); font-size: 14px; line-height: 1.5; }
.hero-pills { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding-top: 6px; }
.account { display: flex; justify-content: flex-end; align-items: center; gap: 8px; font-size: 13px; margin-top: -6px; }
.account a { color: var(--link-text-color); }
.pill-label { font-size: 12px; color: var(--body-text-color-subdued); margin-left: 6px; }

.pill { display: inline-flex; align-items: center; padding: 1px 9px; border-radius: 999px; font-size: 12px; font-weight: 550;
  line-height: 20px; white-space: nowrap; border: 1px solid transparent; vertical-align: middle; }
.pill-neutral { background: rgba(100,116,139,.12); color: var(--body-text-color); border-color: rgba(100,116,139,.25); }
.pill-green { background: rgba(22,163,74,.10); color: #15803d; border-color: rgba(22,163,74,.30); }
.pill-amber { background: rgba(217,119,6,.10); color: #b45309; border-color: rgba(217,119,6,.30); }
.pill-red { background: rgba(220,38,38,.08); color: #b91c1c; border-color: rgba(220,38,38,.30); }
.pill-blue { background: rgba(79,70,229,.08); color: #4338ca; border-color: rgba(79,70,229,.25); }
.dark .pill-green { color: #4ade80; } .dark .pill-amber { color: #fbbf24; }
.dark .pill-red { color: #f87171; } .dark .pill-blue { color: #a5b4fc; }

.toolbar { align-items: center !important; margin-bottom: -4px; }
.stepper { display: flex; flex-wrap: wrap; align-items: center; list-style: none; margin: 0 !important; padding: 0 !important; row-gap: 6px; }
.stepper .step { display: flex; align-items: center; gap: 8px; margin: 0 !important; padding: 0 !important;
  font-size: 13px; color: var(--body-text-color-subdued); }
.stepper .step:not(:last-child)::after { content: ""; width: 26px; height: 2px; margin: 0 10px; border-radius: 2px; background: var(--border-color-primary); }
.stepper .dot { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; font-size: 11px; font-weight: 700;
  border: 1.5px solid var(--border-color-primary); background: var(--block-background-fill); }
.stepper .step-done { color: var(--body-text-color); }
.stepper .step-done .dot { background: #6366f1; border-color: #6366f1; color: #fff; }
.stepper .step-done:not(:last-child)::after { background: #6366f1; }
.stepper .step-active, .stepper .step-warn { color: var(--body-text-color); font-weight: 600; }
.stepper .step-active .dot { border-color: #6366f1; color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,.18); }
.stepper .step-warn .dot { border-color: #d97706; color: #d97706; box-shadow: 0 0 0 3px rgba(217,119,6,.18); }

.card { border: 1px solid var(--border-color-primary); border-radius: 12px; padding: 14px 16px; background: var(--block-background-fill); }
.card.flat { border: none; padding: 14px 16px 4px; }
.card-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-weight: 600; font-size: 14px; margin-bottom: 10px; }
.muted { color: var(--body-text-color-subdued); font-weight: 400; font-size: 13px; }
.bar { height: 4px; border-radius: 4px; background: var(--border-color-primary); overflow: hidden; margin-bottom: 8px; }
.bar > div { height: 100%; background: #6366f1; transition: width .4s ease; }
.props { margin: 0; }
.prop { display: grid; grid-template-columns: 104px 1fr; gap: 10px; padding: 7px 0; border-top: 1px solid var(--border-color-primary); font-size: 13px; }
.prop:first-child { border-top: none; }
.prop dt { margin: 0; color: var(--body-text-color-subdued); }
.prop dd { margin: 0; word-break: break-word; }
.err { color: #dc2626; font-size: 12px; margin-top: 2px; }
.card-foot { margin-top: 8px; font-size: 12px; color: var(--body-text-color-subdued); font-family: var(--font-mono); }
.card code { font-size: 12px; }
.section-label { margin: 12px 0 4px; font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--body-text-color-subdued); }
.sources, .risks { list-style: none; margin: 0 !important; padding: 0 !important; font-size: 13px; }
.sources li { margin: 0 !important; padding: 7px 0; border-top: 1px solid var(--border-color-primary); }
.sources li:first-child { border-top: none; }
.risks li { position: relative; margin: 0 !important; padding: 3px 0 3px 20px; }
.risks li::before { content: "⚠"; position: absolute; left: 0; color: #d97706; }
.meta { margin-top: 3px; font-size: 12px; color: var(--body-text-color-subdued); }
.meta.note { margin: -4px 0 8px; }
.callout { margin-bottom: 4px; padding: 8px 10px; border-radius: 8px; font-size: 13px; background: rgba(22,163,74,.10); }

.review-box, .result-box, .draft-box { border: 1.5px solid #6366f1 !important; border-radius: 12px !important; overflow: hidden;
  box-shadow: 0 6px 20px rgba(79,70,229,.10); margin-bottom: 12px; }
.result-title { padding: 12px 16px 4px !important; }
.draft-box > .prose:first-child { padding: 12px 16px 0 !important; }
.result-title h3 { margin: 0 0 6px; font-size: 16px; }
.us-preview { max-height: 50vh; overflow: auto; }

/* Example prompts in the empty chat as clickable cards. */
#chat .examples { gap: 10px !important; }
#chat .examples .example { border: 1px solid var(--border-color-primary) !important; border-radius: 12px !important;
  padding: 12px 14px !important; background: var(--block-background-fill) !important; text-align: left;
  transition: border-color .15s, box-shadow .15s, transform .15s; }
#chat .examples .example:hover { border-color: #6366f1 !important; box-shadow: 0 4px 14px rgba(79,70,229,.12); transform: translateY(-1px); }

/* Phone: step tracker shows dots only, plus the current step's name. */
@media (max-width: 640px) {
  .toolbar { flex-wrap: wrap !important; }
  .toolbar > * { min-width: 100% !important; }
  .stepper .step > span:last-child { display: none; }
  .stepper .step-active > span:last-child, .stepper .step-warn > span:last-child { display: inline; }
  .stepper .step:not(:last-child)::after { width: 12px; margin: 0 6px; }
}
"""
