import gradio as gr
import sys
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

KO_FI = "https://ko-fi.com/outclaw"

def run_irac(issue, facts, jurisdiction):
    if not issue.strip() or not facts.strip():
        return "Please fill in Issue and Facts."
    try:
        from outclaw_irac import analyze
        return analyze(issue=issue, facts=facts, jurisdiction=jurisdiction)
    except (ImportError, AttributeError):
        return f"ISSUE\n{issue}\n\nRULE\nApplicable law in {jurisdiction} jurisdiction.\n\nANALYSIS\nBased on: {facts}\n\nCONCLUSION\nDocument all evidence. This warrants further legal research."

def run_foia(agency, subject, date_range):
    if not agency.strip() or not subject.strip():
        return "Please fill in Agency and Subject."
    today = datetime.date.today().strftime("%B %d, %Y")
    dr = f"Date Range: {date_range}" if date_range.strip() else ""
    return f"FREEDOM OF INFORMATION ACT REQUEST\n\nDate: {today}\n\n{agency}\nFOIA Officer\n\nPursuant to 5 U.S.C. § 552, I request all records related to:\n\nSubject: {subject}\n{dr}\n\nI request a fee waiver. Acknowledge within 20 business days.\n\nRespectfully,\n[YOUR NAME]"

def run_grievance(incident, respondent, relief):
    if not incident.strip() or not respondent.strip():
        return "Please fill in Incident and Respondent."
    today = datetime.date.today().strftime("%B %d, %Y")
    return f"FORMAL GRIEVANCE\n\nDate: {today}\nTo: {respondent}\n\nSTATEMENT:\n{incident}\n\nRELIEF SOUGHT:\n{relief or '[Describe desired outcome]'}\n\nIf unresolved in 30 days, I reserve all legal remedies.\n\n[YOUR NAME]"

def run_scorer(issue, facts):
    if not issue.strip() or not facts.strip():
        return "Please fill in Issue and Facts."
    strong = ["documented","written","contract","email","signed","witness","recorded","receipt"]
    weak = ["verbal","no proof","lost","unclear","maybe","alleged"]
    val = 50
    for k in strong:
        if k in facts.lower(): val += 8
    for k in weak:
        if k in facts.lower(): val -= 10
    val = max(10, min(95, val))
    label = "STRONG" if val >= 70 else "MODERATE" if val >= 45 else "WEAK"
    advice = {"STRONG":"Well-documented. Proceed.","MODERATE":"Gather more evidence.","WEAK":"Significant gaps. Consult legal aid."}[label]
    return f"Case Strength: {label} ({val}/100)\n\nAdvice: {advice}"

with gr.Blocks(theme=gr.themes.Monochrome(), title="OutClaw Legal AI") as demo:
    gr.Markdown(f"# ⚖️ OutClaw Legal AI\nFree pro se legal tools. No signup.\n[Support on Ko-fi]({KO_FI})")
    with gr.Tab("IRAC Analysis"):
        i1 = gr.Textbox(label="Legal Issue", lines=2)
        i2 = gr.Textbox(label="Key Facts", lines=2)
        i3 = gr.Dropdown(["federal","state","civil","criminal","administrative"], value="federal", label="Jurisdiction")
        b1 = gr.Button("Analyze", variant="primary")
        o1 = gr.Textbox(label="Result", lines=12, interactive=False)
        b1.click(run_irac, inputs=[i1,i2,i3], outputs=o1)
    with gr.Tab("FOIA Request"):
        f1 = gr.Textbox(label="Agency")
        f2 = gr.Textbox(label="Subject", lines=2)
        f3 = gr.Textbox(label="Date Range (optional)")
        b2 = gr.Button("Generate FOIA Letter", variant="primary")
        o2 = gr.Textbox(label="FOIA Letter", lines=20, interactive=False)
        b2.click(run_foia, inputs=[f1,f2,f3], outputs=o2)
    with gr.Tab("Grievance Letter"):
        g1 = gr.Textbox(label="Describe the Incident", lines=3)
        g2 = gr.Textbox(label="Respondent")
        g3 = gr.Textbox(label="Relief Sought")
        b3 = gr.Button("Draft Grievance", variant="primary")
        o3 = gr.Textbox(label="Grievance Letter", lines=20, interactive=False)
        b3.click(run_grievance, inputs=[g1,g2,g3], outputs=o3)
    with gr.Tab("Case Scorer"):
        s1 = gr.Textbox(label="Legal Issue", lines=2)
        s2 = gr.Textbox(label="Supporting Facts", lines=3)
        b4 = gr.Button("Score My Case", variant="primary")
        o4 = gr.Textbox(label="Case Strength", lines=6, interactive=False)
        b4.click(run_scorer, inputs=[s1,s2], outputs=o4)
    gr.Markdown("---\n*Not a law firm. Consult a licensed attorney for serious matters.*")

if __name__ == "__main__":
    demo.launch()
