# How we used AI

We used ChatGPT and Claude pretty extensively while working on this project. We came up with the research question, experimental setup, codebase structure, and testing goals. We used AI to challenge and refine those ideas, help turn our specifications into code implementations, troubleshoot issues, interpret preliminary results, and draft and edit much of the report. We made the final decisions about what to test, how to run the experiment, and how to interpret the results.

This file gives a more detailed explanation of the process, including the important prompts we could recover and how we checked the work. It goes with the shorter AI usage statement in the `README.md`.

## What we used AI for

| Part of the project     | What we did                                                                                                                                                     | How AI helped                                                                                                       |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Research idea           | Started with a question about conflicting information in LLM context and decided what behavior to measure.                                                      | Challenged the scope and suggested ways to make the variables measurable.                                           |
| Exploratory experiments | Chose scenarios, models, and runs, and inspected where the initial experiments were too easy or too complicated.                                                | Helped plan exploratory runs, interpret failures, and simplify the task.                                            |
| Final experiment        | Chose to focus on budget records, withdrawals, unauthorized claims, matched log versions, an optional guidance instruction, and repeated calls.                 | Pointed out confounds and statistical weaknesses, suggested controls, and critiqued alternative designs.            |
| Code                    | Specified the architecture and expected behavior, then used AI-assisted coding to implement and revise the generator, experiment runner, scoring, and analysis. | Generated much of the implementation from our instructions and assisted with debugging and tests.                   |
| Testing and review      | Ran validation checks, pilots, and experimental calls; checked outputs and reviewed whether the results matched the intended design.                            | Suggested edge cases and additional checks, and helped investigate unexpected results and implementation decisions. |
| Report                  | Decided what findings and limitations to present and checked the claims against the experiment.                                                                 | Drafted substantial parts of the prose and helped revise terminology, structure, explanations, and LaTeX.           |

The LLMs evaluated _in the experiment_ are separate from the AI assistants used to _develop_ the experiment. For example, a model answering a synthetic budget question is experimental data, while asking ChatGPT or Claude to review our statistics is AI-assisted development.

## Important prompts and what came out of them

Here are 13 ChatGPT conversations and 6 Claude conversations and selected prompts that helped us with the research question, experiment, implementation, validation, analysis, or report. The excerpts below use our original wording, apart from a few bracketed name redactions. Some messages also contained long pasted proposals, report drafts, code, or result tables. We summarize that extra context instead of reproducing it all. We left out routine follow-ups, repeated requests, and minor formatting questions.

Each entry names the AI tool and explains what we asked and what we did with the response. The entries are grouped by topic.

### A. Coming up with the idea and finding a task that was actually hard

**1. Initial research question (Claude)**

> so i need to have a topic for my senior capston. im in section 21. and this week we need to basically come up with an idea of smth we want to test on a LLM. i kinda came up with smth last week but it was really rough and now i also have a partner. ive since then refined it. do u think this is a good starting point? or do u want to change smth?

The message went on to describe our original idea: testing whether an LLM follows incorrect or contradictory information, with the amount/type of conflicting information as a possible independent variable and correctness as the outcome. Claude helped narrow this into a measurable experiment. The core topic was ours while we figure out the precise design choice.

**2. Early exploratory proposal (Claude)**

> im currently in dsc 180a, and this below is our research question. for now, we need to do like preliminary exploratory findings and we dont really care about formal methodology, but rather kinda like an EDA thing.

We asked for help setting up exploratory experiments before committing to the final methodology. Later in the same conversation, we asked for critiques and revisions of a detailed preliminary proposal, including source reliability, misleading context, controls, and a reusable conflict-resolution instruction. These were design reviews, not actual evidence that the proposed design worked.

**3. Escalating difficulty after near-perfect results (Claude)**

> ok so like ive conducted everything in stage 0. and as expected, modern SOTA llms are way too smart and they got literally everything correct for every rung. so idk what to do now. we need to ramp up the diffuclty by at least 100 fold

Our first simple contradictions barely broke stronger models. We used AI to brainstorm harder tasks and then tried larger, more complicated records. Those exploratory runs eventually motivated our final design, but we didn't use their accuracy as part of the final study.

**4. Simplifying after the first EDA (Claude)**

> so this was my initial eda for my dsc180a capstone. as u can see it didnt lead to much, and my prof wants interesting results while keeping it simple

In this message to Claude, we also pasted a write-up describing our earlier exploratory experiments and results. The write-up summarized the tasks. Claude suggested simplifying the multi-project task into tracking one changing value, and mentioned using budget amounts instead of dates. We explored that suggestion and developed the eventual budget-log design through further experiments and revisions.

**5. Implementation plan for a harder EDA (Claude)**

> can u give me a detailed high level implementation plan for it for me to throw it to claude code? i suppose the first thing we want is to break as much models as we can first and then move forward from there? please look at the current github repo

We asked for a plan that could be handed to Claude Code. The resulting discussion include a synthetic generator, matched controls, withdrawal chains, output formats, and preliminary checks. This was a planning/handoff conversation.

### B. Consolidating our experiments and fixing design problems

**6. Comparing the separate implementations (Claude)**

> which direction has the most potential of like actually having interesting results / how should we two consolidate and converge into smth / make it more rigorous from there. the thing is we have to make it simple enough that the prof would still understand and without overengineering it.

We asked AI to compare the two exploratory approaches and critique which pieces were worth keeping. The main takeaway was to consolidate around the budget-log task, use matched versions, and separate the effect of withdrawals from that of unauthorized claims. We reviewed the tradeoffs before narrowing the design.

**7. Planning the matched conditions, skill, and repeated calls (Claude)**

> how should we consolidate into like a more well structured / towards our final experiemnt that is well designed? one thing we want to do is to identify failures, and also the prof wants more repeats of the same prompts to see if there are variability / consistency. what is the best way to set this up? also skills/without should be in this experiment as well. and im not sure if we want to still have n to be our indep variable?

This led to a fixed-length and log matching design. We eventually settled on using clean (`C`), withdrawal (`R`), withdrawal+gossip (`RG`), and explicit reversal (`E`) versions, with and without an additional instruction. We also planned repeated independent calls and discussed why the log, rather than each repeat, should be the unit for paired statistical comparisons.

**8. Choosing and questioning the fixed log length (Claude)**

> what do u think the N should be fixed at? my experiments results look smth like this graph, but also look at [my teammate's] if available in the repo. im guessing we'll be using opus and astra only for now, but idk what reasoning level (either low or medium). and the fixation of these things should also be brought up i think. all of my experiments were ran at low

This prompt included an exploratory accuracy vs length graph. We discussed using a fixed 1,600 record setting and low reasoning effort, then checking those settings in a separate trial before the main runs. The goal was to avoid mixing the effect of log length with the effect of withdrawal wording.

**9. Critiquing AI-generated implementation choices (Claude)**

> these are the choices that the claude code model made while doing the consolidation. do u think these make sense or should something be changed? i dont quite understand these changes / if they have any benefits vs we should just do what we originally intended.

The original prompt continued with concrete questions about unique amounts, whether gossip should be absolute or relative, dates, and call scheduling. We did not automatically accept the coding assistant's choices. We reviewed them against our intended experiment and requested revisions where the code/design drifted from that goal.

**10. A confound in clean versus withdrawal logs (Claude)**

> so is this experiment design u proposed actually robust / can show actual good inference or perhaps causality now or is it still handwavy

We challenged whether the matched versions really isolated the effect we wanted. In particular, `R` versus `C` changes more than just the wording of withdrawals: `R` also contains changes that later get cancelled. This discussion motivated `E`, where those withdrawals are expressed as explicit arithmetic adjustments, and encouraged us to be careful about causal claims.

**11. Asking for the actual implementation changes (Claude)**

> so check the current github main branch. what needs to be implemented / changed? give me what i should send to my claude code pretty much

We used AI to turn the design into a coding handoff. The requested changes included the `E` variant, matched answers and lengths, comparable scoring signatures, a configurable skill arm, and paired statistical analysis. Later follow-ups simplified the handoff, removed unnecessary options, and asked for clean, modular code. These are prompts used to _prepare_ coding instructions; the exports do not contain every direct Claude Code interaction.

**12. Revisiting the skill design (Claude)**

> so any real benefit for adding G back or is it just bloat? and also whats with the skill thing / why do we want a neutral? i think having a neutral is unncessary currently tbh. and why not jumst have skill v no skill across all categories?

We discussed whether the gossip-only version and a neutral-instruction arm were worth the additional complexity and model calls. We opted to prioritize the main matched versions and skill/no-skill comparisons, with caveats about what a skill effect could establish. This is an example of a design choice made after critiquing an AI suggestion rather than just adding every suggested control.

### C. Testing, debugging, and statistical decisions

**13. Reviewing the first consolidated trial (Claude)**

> ok so like here are the results from the trial run

The prompt included the full `trial_v1` output (40 of 40 planned calls), including accuracy by model/version, preliminary comparisons, failure categories, and token usage. We asked AI to assess the results under good research and statistical practices. This exposed weaknesses in simplistic error buckets, small-sample inference, and the original comparison plan. We kept the trial separate from the main study.

**14. Independent critique of the same trial (ChatGPT)**

> check the main branch of dsc180a capstone, and here are the results from the trial run. thoughts on how to conitnue while following best research and expeirmental design practices?

We took the trial results and design proposals to ChatGPT as a second reviewer, then compared its feedback against Claude's. The back-and-forth discussed sample size, confounding, repeated calls, failure signatures, selection of primary tests, and how much complexity the study actually needed. We used the disagreement to find weak assumptions.

**15. Making enough room for repeatability analysis (Claude)**

> here is A's own analysis. as well as its response to ur analysis. thoughts on this compromise? or is there smth u still want to be different with. also another thing is recall my prof said he wanted a whole lot of repetitions. when we initially presented whatever many repetitions we had before, the prof said to bump that number up a whole notch, so im not sure if 3 (or even 2) will cut it here

We compared competing statistical suggestions and the mentor's request for more repeats. The resulting plan separated the first three repetitions used in primary accuracy tests from a larger descriptive repeatability subset with ten identical calls per selected prompt. We also discussed exact numerical-answer agreement, why repeated calls on one log are not independent logs, and how to avoid changing the primary test based on extra repetitions.

**16. Checking generator and collection fixes (Claude)**

> its response
> I've made changes 1 and 3. `validate` passes and ruff is clean; nothing is committed. Change 2 is waiting on your confirmation of the split below.

The rest of the message pasted the coding assistant's explanation of budget-range fixes, chronological tracking, signed mistake values, and the audit/retry rules. We asked AI to assess whether those fixes preserved the experiment. We also examined the reported comparison of old and new generated logs, including chain-depth and withdrawal distributions.

**18. Reviewing the skill implementation (ChatGPT)**

> can u check if the conflict skill branch is correctly implemented by [my teammate] according to our temporary proposal?

We asked AI to compare the skill branch to our experiment plan, including the instructions, how the skill was passed to models, and whether the implementation matched the study setup. Follow-up prompts checked the main branch and which skill version was intended. This was just used as a code-review aid.

**19. Checking the finished analysis and claims (ChatGPT)**

> can u check the latest github, we have everything now pushed inclduing the analysis of the main experiment. its time to finish writing the paper. ive attached the latex below. recall that there is a 10 page max limit excluding references and appendix, and the reader is likely to have no idea about our experiment.

The prompt included the LaTeX draft. We asked for a review against the latest implementation and experiment results before finishing the report, including whether the reported methods and claims were accurate and understandable. We treated the repository and saved results as the source of truth.

### D. Writing and explaining the report

**20. Drafting the introduction and data overview (ChatGPT)**

> can u help me write the intro and data section based on our temporary proposal that we're using to like construct the experiment, as well as the actual github repo? also idk if the full data construction should be here vs methodology.

AI helped draft the early introduction and decide which details belonged in the introduction versus the methods/data section. We then revised the report as the implementation and experiments changed.

**21. Finding and framing related work (ChatGPT)**

> ok now can u help me do some research and then lets do the related works section. and on top of that, note that in total we have a 10 page max limit excluding appendix, so be sure to size things appropriately.

We used AI to find relevant work and draft a concise literature review. The user message also questioned an earlier citation. We manually went through ALL research GPT provided, checked their validity, read portions of it to determine relevancy, and used them in our literature review as appropriate.

**22. Updating methodology to match the code (ChatGPT)**

> can u check the github repo as well as the temporary proposal doc and help me write the data generation and experimental design parts? the current stuff is kinda wrong cuz it says claude isnt used?

This prompted several rounds of methodology revisions, including model coverage, log construction, experimental conditions, statistical analysis, and pilot versus main-study distinctions. We repeatedly asked for the current repository and results to take priority over older proposals, and to keep the writing short enough for the report limit.

**23. Improving clarity and consistency (ChatGPT)**

> so what is a log, a record, and history? isnt log and history the same thing? did we ever use log?

> ok now this. what is exact answer agreement

We used AI as an editor and explainer while checking terminology and the presentation of results. This included clarifying what a record or log meant, defining exact-answer agreement, and rewriting technical descriptions to be more accessible without changing the underlying analysis.

## How we checked the AI-assisted work

Our main check was whether the code and analysis matched the experimental behavior we had decided on. The conversations show several layers of checking, though here are other checks we've done that isn't obvious from the above conversation:

- **Generator logic:** We asked for independent answer calculations, agreement between two solvers, matching correct answers across log versions, checks on rendered records, and small hand-worked examples (especially nested withdrawals and their explicit reversals). We also reviewed a bug where using the _final_ withdrawal status while generating a log could mishandle the budget at earlier points, then asked for chronological range checks.
- **Matched experimental conditions:** We checked the intended differences among `C`, `R`, `RG`, and `E`, including whether the same underlying budget answer was preserved. We discussed matching prompt length, keeping development seeds separate from the main experiment, and not changing conditions after seeing main-run answers.
- **Error analysis:** We questioned simplistic labels such as “off by one regular change” when many records could produce the same numerical difference. The scoring design was revised toward recording outcome status and potentially overlapping numerical signatures, with clear limits on what those signatures prove.
- **Pilots and final results:** We inspected trial outputs before freezing and running the main experiment, then compared the written conclusions against the saved results. We kept exploratory/trial results conceptually separate from the primary analysis. Repeated calls were analyzed as repeats of the same prompt, not as independent scenarios.
- **Statistics:** We used AI to critique the unit of analysis, paired comparisons, bootstrap confidence intervals, sign-flip tests, Holm correction for multiple primary tests, ceiling effects, and descriptive repeatability measures. We reviewed the reasoning and retained responsibility for the tests and claims in the report.
- **Report:** We checked the AI drafted sections of the report end to end against the repository, results, and the evolution of our study design, and revised confusing or outdated parts. AI generated substantial initial draft, but we manually went through the paper end to end, and update sections where it didn't make sense, had terminology issues, presentation accuracy, and so on.

## What we didn't treat AI as evidence for

We did not assume an AI suggestion was correct. We challenged a lot of its suggestions, asked different assistants to critique one another, rejected extra conditions that would have bloated the experiment, and changed earlier plans when pilots or implementation details revealed new problems. Suggestions about a possible failure mechanism were treated as hypotheses or descriptive clues unless the matched experiment actually supported them.
