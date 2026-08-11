#!/usr/bin/env python3
"""outclaw_pro_se_course.py — plain-language court-mechanics course.

A self-study course for self-represented litigants: how courts actually
work, in common language. Covers what a court has authority over, why the
record matters, how to object, how to allege and prove facts, and how to
prepare for the moments of trial — oral argument, opening and closing
statements, witness questioning, and depositions.

ADVISORY ONLY. This is study material, not legal advice, not a legal
validation, and not authorization to file anything. State-specific rules
vary; where a lesson touches local procedure it says so instead of
guessing. Nothing here replaces the court's rules, the judge's
instructions, or a licensed attorney's judgment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

_ADVISORY = {"advisory": True, "study_material_only": True}


@dataclass
class Lesson:
    """One study lesson: plain-language explanation + what to do."""

    key: str
    title: str
    plain_language: list[str] = field(default_factory=list)
    why_it_matters: list[str] = field(default_factory=list)
    do_this: list[str] = field(default_factory=list)
    common_mistakes: list[str] = field(default_factory=list)
    key_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "plain_language": self.plain_language,
            "why_it_matters": self.why_it_matters,
            "do_this": self.do_this,
            "common_mistakes": self.common_mistakes,
            "key_terms": self.key_terms,
        }


class ProSeCourse:
    """Structured plain-language lessons + glossary + trial-prep tracks.

    Study material only. Every public method returns advisory-labeled,
    JSON-safe output.
    """

    # ------------------------------------------------------------------
    # Plain-language glossary (term -> plain definition)
    # ------------------------------------------------------------------
    GLOSSARY: dict[str, str] = {
        "jurisdiction": "A court's lawful authority over a case. A court can only act within the power the law gives it — subject-matter (what kind of case) and personal (over whom).",
        "subject-matter jurisdiction": "Whether this court is the right kind of court for this kind of case (e.g. criminal vs. civil, state vs. federal).",
        "personal jurisdiction": "Whether this court has lawful authority over this particular person.",
        "venue": "Which courthouse in the right court system hears the case (a practical location question, separate from jurisdiction).",
        "the record": "The official written account of everything said, offered, and ruled in the case. If it is not on the record, for appeal purposes it did not happen.",
        "objection": "A timely statement that evidence or a question is improper under the rules, made on the record so the judge rules and the point is preserved.",
        "hearsay": "An out-of-court statement offered to prove the truth of what it says. Generally inadmissible unless an exception or exclusion applies.",
        "admissible": "Allowed into evidence under the rules of evidence.",
        "foundation": "The preliminary showing that evidence is what you say it is and was obtained or handled properly.",
        "leading question": "A question that suggests its own answer (\"You were there, weren't you?\"). Allowed on cross-examination, not normally on direct.",
        "open-ended question": "A question that lets the witness tell the story in their own words (\"What happened next?\"). The tool of direct examination.",
        "impeachment": "Attacking a witness's credibility — showing a prior inconsistent statement, bias, or a reason their account is unreliable.",
        "discovery": "The pre-trial process of exchanging information and evidence with the other side.",
        "interrogatories": "Written questions the other side must answer in writing, under oath.",
        "requests for admission": "Written statements the other side must admit or deny; admissions become facts in the record.",
        "motion": "A formal request asking the judge to rule on something (dismiss, strike, compel, suppress, etc.).",
        "affidavit": "A written statement made under oath.",
        "pleading": "The formal papers that frame the dispute (complaint, answer, etc.).",
        "burden of proof": "Which side must prove what, and to what standard. In a criminal trial the state must prove guilt beyond a reasonable doubt.",
        "beyond a reasonable doubt": "The criminal standard: the state must prove the elements of the crime so thoroughly that no reasonable doubt remains.",
        "exhibit": "A physical or documentary item marked and offered into evidence.",
        "stipulation": "An agreement between the parties on a fact or procedure, put on the record.",
        "continuance": "A postponement of a hearing or trial.",
        "pro se": "Representing yourself, without a lawyer.",
        "voir dire": "The process of questioning prospective jurors to select an impartial jury.",
        "mistrial": "A trial ended without a verdict (e.g. a hung jury or prejudicial error), which may be retried.",
        "direct examination": "Questioning your own witness. Use open-ended questions; the witness, not the lawyer, tells the story.",
        "cross-examination": "Questioning the other side's witness. Use leading questions to pin down specific facts.",
        "standard of review": "How much deference an appellate court gives the trial court's decision (e.g. de novo for law, clear error for fact).",
    }

    # ------------------------------------------------------------------
    # Lessons
    # ------------------------------------------------------------------
    LESSONS: dict[str, Lesson] = {
        "jurisdiction": Lesson(
            key="jurisdiction",
            title="What a court is allowed to do",
            plain_language=[
                "Jurisdiction is the boundary of a court's lawful power. Before a court can act against you, the law has to give it authority over the case (subject-matter) and over you (personal).",
                "This is not a magic trick. It is a real, checkable requirement: the court's authority comes from statutes and rules, and it either exists or it doesn't.",
                "If a court lacks jurisdiction, its orders are void — but the correct way to raise that is through the proper motion and the record, not by refusing to participate.",
            ],
            why_it_matters=[
                "Filing in the wrong court wastes time and can cost you the case on a technicality.",
                "Raising jurisdiction properly — in the answer, by motion, on the record — preserves the issue.",
            ],
            do_this=[
                "Identify the court and confirm it hears this kind of case (criminal vs. civil; state vs. federal).",
                "Check personal jurisdiction: did the court get lawful authority over the person named?",
                "Raise defects by motion or in the answer, on the record, and follow the court's rules for doing so.",
            ],
            common_mistakes=[
                "Treating jurisdiction as a slogan instead of a legal argument with citations.",
                "Refusing to appear and then calling every order void — that abandons the record and invites default.",
            ],
            key_terms=["jurisdiction", "subject-matter jurisdiction", "personal jurisdiction", "venue"],
        ),
        "the_record": Lesson(
            key="the_record",
            title="The record is everything",
            plain_language=[
                "The record is the official account of the case. What is on the record can be appealed; what is not might as well not have happened.",
                "Judges rule from the record and appellate courts review the record. Your job in every hearing is to put your points on the record clearly and timely.",
            ],
            why_it_matters=[
                "An error you did not preserve is an error you cannot raise on appeal.",
                "A clean record is the difference between a strong appeal and a dead one.",
            ],
            do_this=[
                "Make objections on the record, stating a legal basis, before the evidence comes in.",
                "If the judge rules against you, ask to make an offer of proof (what the evidence would have shown).",
                "Keep your own accurate notes of each hearing and what was said on the record.",
            ],
            common_mistakes=[
                "Objecting after the answer is already in — too late to prevent the jury hearing it.",
                "Arguing with the judge instead of stating the objection and letting the record speak.",
            ],
            key_terms=["the record", "objection", "offer of proof"],
        ),
        "objections": Lesson(
            key="objections",
            title="Objecting the right way",
            plain_language=[
                "An objection tells the judge the question or evidence is improper, and gives a legal reason. It is timely (before the answer or the evidence), specific, and on the record.",
                "The point of objecting is twofold: keep improper evidence out, and preserve the issue for appeal if the judge overrules you.",
            ],
            why_it_matters=[
                "The rules of evidence decide what the fact-finder is allowed to consider.",
                "Objecting protects the record even when the judge rules against you.",
            ],
            do_this=[
                "Object before the witness answers or the exhibit is admitted.",
                "Name the reason: hearsay, leading on direct, no foundation, relevance, speculation.",
                "Accept the ruling calmly, note it for the record, and move on.",
            ],
            common_mistakes=[
                "Objecting late, or objecting with no stated basis.",
                "Rattling off objections to everything — it wastes credibility with the fact-finder.",
            ],
            key_terms=["objection", "hearsay", "foundation", "admissible"],
        ),
        "alleging_facts": Lesson(
            key="alleging_facts",
            title="Stating the facts that matter",
            plain_language=[
                "Pleadings state facts, not conclusions. Each claim has legal elements, and your pleading should state facts that fit those elements — who, what, when, where, how.",
                "A conclusion (\"the defendant is liable\") proves nothing. Facts (\"on the date, at the place, the defendant did this\") are what the law can work with.",
            ],
            why_it_matters=[
                "A pleading that states facts matching the elements survives challenge and frames what you must prove.",
                "Sloppy allegations can be attacked and dismissed.",
            ],
            do_this=[
                "List the elements of each claim or charge.",
                "Under each element, write the specific facts that satisfy it.",
                "Keep it plain and complete: dates, names, places, and what happened.",
            ],
            common_mistakes=[
                "Writing arguments instead of facts in a pleading.",
                "Copying boilerplate that does not match your actual facts.",
            ],
            key_terms=["pleading", "elements", "complaint", "answer"],
        ),
        "proving_facts": Lesson(
            key="proving_facts",
            title="Proving the facts",
            plain_language=[
                "Facts are only proven by admissible evidence: testimony from witnesses who saw or know, documents with foundation, and exhibits the court admits.",
                "Hearsay and other inadmissible evidence does not count, no matter how true it sounds.",
            ],
            why_it_matters=[
                "The fact-finder can only consider what the rules let in.",
                "Your case is as strong as the admissible evidence behind each element.",
            ],
            do_this=[
                "Map each fact you must prove to the evidence that proves it.",
                "Prepare foundation for each document before you offer it.",
                "Know the hearsay exceptions that might apply to your evidence.",
            ],
            common_mistakes=[
                "Assuming documents speak for themselves — they need a witness and foundation.",
                "Counting on evidence that will be excluded as hearsay.",
            ],
            key_terms=["admissible", "foundation", "hearsay", "exhibit"],
        ),
        "discovery": Lesson(
            key="discovery",
            title="Making the other side show their cards",
            plain_language=[
                "Discovery is the pre-trial process of exchanging information: documents, written questions, admissions, and depositions.",
                "Done well, it pins the other side to facts and surfaces what they will say before trial.",
            ],
            why_it_matters=[
                "Surprise is the enemy of a pro se litigant. Discovery turns surprise into preparation.",
                "Requests for admission can lock in facts that simplify trial.",
            ],
            do_this=[
                "Request the documents and records that matter to your elements.",
                "Use requests for admission on facts you believe are undisputed.",
                "Answer discovery on time — missed deadlines can forfeit your position.",
            ],
            common_mistakes=[
                "Ignoring discovery requests or responding late.",
                "Failing to use discovery to pin down the other side's witnesses.",
            ],
            key_terms=["discovery", "interrogatories", "requests for admission", "deposition"],
        ),
        "trial_order": Lesson(
            key="trial_order",
            title="How a trial actually moves",
            plain_language=[
                "A trial follows an order: jury selection, opening statements, the prosecution's/plaintiff's case, the defense case, closing arguments, instructions, verdict.",
                "Knowing the order tells you when your moments are and what each part is for.",
            ],
            why_it_matters=[
                "The order is the map. Openings preview, evidence proves, closings connect.",
                "You cannot do in closing what you failed to do in evidence.",
            ],
            do_this=[
                "Prepare for each phase in order: openings, then evidence, then closings.",
                "Listen to the judge's instructions on procedure and follow them.",
                "Preserve objections at every phase, including during the other side's case.",
            ],
            common_mistakes=[
                "Arguing the case in the opening statement.",
                "Saving arguments for closing that were never supported by evidence.",
            ],
            key_terms=["voir dire", "opening statement", "closing argument", "verdict"],
        ),
    }

    # ------------------------------------------------------------------
    # Trial-prep tracks (structured practice plans)
    # ------------------------------------------------------------------
    PREP_TRACKS: dict[str, dict[str, Any]] = {
        "oral-argument": {
            "title": "Oral argument",
            "goal": "Persuade the judge with a clear, honest answer to the question that decides the case.",
            "structure": [
                "Open with the one sentence that states what you are asking and why.",
                "Give the roadmap: the issue, the rule, how the facts fit.",
                "Make your best point first, then support it.",
                "Answer the judge's questions directly — they are the point of argument.",
                "Close by restating what you are asking the court to do.",
            ],
            "do": ["Prepare for the hardest question and answer it head-on.", "Pause after the judge speaks.", "Know the record and the standard of review."],
            "avoid": ["Reading a script word-for-word.", "Avoiding the judge's question.", "Arguing facts the record does not support."],
        },
        "opening": {
            "title": "Opening statement",
            "goal": "Tell the fact-finder what the evidence will show — a preview, not an argument.",
            "structure": [
                "Give the theme in one plain sentence.",
                "Preview the story the evidence will tell, in order.",
                "Preview the key evidence and witnesses that will carry it.",
                "End with what you will ask them to find.",
            ],
            "do": ["Promise only what the evidence will deliver.", "Use plain language.", "Keep it tight."],
            "avoid": ["Arguing or editorializing.", "Overpromising evidence you cannot produce."],
        },
        "closing": {
            "title": "Closing argument",
            "goal": "Connect the admitted evidence to each element and ask for the verdict.",
            "structure": [
                "Remind them of the theme.",
                "Walk each element and point to the evidence that proves it.",
                "Address the weakness in your case before they do.",
                "Answer the burden of proof directly and ask for the specific result.",
            ],
            "do": ["Only argue what is actually in the record.", "Acknowledge and defuse weaknesses.", "End with a concrete ask."],
            "avoid": ["Introducing new facts.", "Personal attacks.", "Losing your place by rushing."],
        },
        "direct-exam": {
            "title": "Direct examination",
            "goal": "Let your witness tell the story in their own words, with the facts your elements need.",
            "structure": [
                "Lay foundation: who they are and how they know what they know.",
                "Move chronologically with short, open-ended questions.",
                "One fact per question; let them answer.",
                "Introduce documents through foundation before offering them.",
            ],
            "do": ["Prepare the witness to answer plainly and honestly.", "Stop when the point is made.", "Listen to the answer."],
            "avoid": ["Leading your own witness.", "Asking compound or confusing questions.", "Coaching the answer in the question."],
        },
        "cross-exam": {
            "title": "Cross-examination",
            "goal": "Pin down specific facts with leading questions — control the witness, don't argue.",
            "structure": [
                "Ask short, leading questions that call for yes/no.",
                "Lock in the facts that help you, one at a time.",
                "If you have a prior inconsistent statement, confront the witness with it on the record.",
                "Stop when you have what you need.",
            ],
            "do": ["Have a plan of the points you need to lock in.", "Use the record and documents to impeach.", "End on a strong note."],
            "avoid": ["Asking 'why' on cross — it gives the witness the floor.", "Attacking the witness personally.", "Fishing without a plan."],
        },
        "deposition": {
            "title": "Deposition prep",
            "goal": "Take sworn testimony before trial to learn what the witness will say and pin it down.",
            "structure": [
                "Prepare your outline: the topics and the facts you need confirmed.",
                "Ask open questions to let them talk; follow up on the details that matter.",
                "Get specifics — dates, times, names, words, amounts — on the record.",
                "Make objections for the record (form, foundation) without coaching the witness.",
            ],
            "do": ["Know the case file before you start.", "Get commitments you can use at trial.", "Read the transcript after for inconsistencies."],
            "avoid": ["Letting the witness ramble past the point.", "Telling the witness what to say.", "Leaving a question you need on the table."],
        },
    }

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def course_index(self) -> dict[str, Any]:
        return {
            **_ADVISORY,
            "lessons": [lesson.to_dict() for lesson in self.LESSONS.values()],
            "prep_tracks": {k: v["title"] for k, v in self.PREP_TRACKS.items()},
            "glossary_terms": len(self.GLOSSARY),
        }

    def get_lesson(self, key: str) -> Optional[dict[str, Any]]:
        lesson = self.LESSONS.get(key)
        if lesson is None:
            return None
        return {**_ADVISORY, "lesson": lesson.to_dict()}

    def lookup_term(self, term: str) -> Optional[dict[str, Any]]:
        normalized = term.strip().lower()
        for key, definition in self.GLOSSARY.items():
            if normalized in (key, key.lower()):
                return {**_ADVISORY, "term": key, "definition": definition}
        return None

    def prep_track(self, key: str) -> Optional[dict[str, Any]]:
        track = self.PREP_TRACKS.get(key)
        if track is None:
            return None
        return {**_ADVISORY, "track": key, **track}

    def trial_prep_pack(self) -> dict[str, Any]:
        # Advisory metadata only: probe the objections engine rather than
        # claim availability the module never verifies.
        try:
            import importlib.util

            objections_available = (
                importlib.util.find_spec("outclaw_objections_engine") is not None
            )
        except Exception:
            objections_available = False
        return {
            **_ADVISORY,
            "pack": "full",
            "tracks": self.PREP_TRACKS,
            "objections_engine_available": objections_available,
        }

    def related_lessons(self, key: str) -> dict[str, Any]:
        """Lessons that pair with a prep track (e.g. cross-exam -> objections)."""
        related = {
            "oral-argument": ["jurisdiction", "the_record"],
            "opening": ["trial_order", "alleging_facts"],
            "closing": ["proving_facts", "trial_order"],
            "direct-exam": ["proving_facts", "the_record"],
            "cross-exam": ["objections", "proving_facts"],
            "deposition": ["discovery", "the_record"],
        }
        return {
            **_ADVISORY,
            "track": key,
            "related_lessons": related.get(key, []),
        }


COURSE = ProSeCourse()
