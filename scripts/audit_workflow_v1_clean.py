"""Audit existing workflow-v1 clean responses; makes no model calls. Run from repo root with PYTHONPATH=."""
import csv,json,re,statistics
from pathlib import Path
from collections import defaultdict
from experiment.runs import load,read_attempts,counted
from experiment.scoring import score
from experiment.world import World
run=load(Path('runs/conflict_workflow_v1_pilot_v1')); done=counted(read_attempts(run));rows=[];summaries=[];groups=defaultdict(list)
for t in run.trials:
 if t.version!='C':continue
 a=done[t.trial_id];result=score(a['response'],run.keys[t.world_id],False)
 w=World.from_json(json.loads((run.path/'worlds'/f'{t.world_id}.json').read_text()));records=w.version('C');opening=records[0].amount
 text=a['response'];cumulative=False; trialrows=[]
 for line in text.splitlines():
  cells=[c.strip() for c in line.split('|')[1:-1]]
  if len(cells)>1 and (cells[0].startswith('Records') or cells[0]=='Record range'):
   cumulative=cells[1].startswith('Budget at end') or cells[1]=='Budget'
  m=re.match(r'\|\s*#?(\d{4})[–−-]#?(\d{4})\s*\|([^|]+)',line)
  if not m:continue
  start,end=int(m[1]),int(m[2]);value=m[3].replace(',','').replace('−','-').replace('$','').replace('**','').replace('K','').strip()
  number=re.match(r'[+-]?\d+',value)
  if not number:raise ValueError((t.trial_id,line))
  reported=int(number[0])
  expected=(opening+sum(r.amount for r in records if r.kind=='adjust' and r.id<=end)) if cumulative else sum(r.amount for r in records if r.kind in ('opening','adjust') and start<=r.id<=end)
  row=dict(trial=t.trial_id,instruction=t.instruction,correct=result['correct'],start=start,end=end,kind='running_state' if cumulative else 'segment_change',reported=reported,expected=expected,error=reported-expected)
  rows.append(row);trialrows.append(row)
 groups[t.world_id,t.instruction].append((result,a,len(trialrows)))
 if not result['correct']:
  bad=[r for r in trialrows if r['error']]
  recombined=None if cumulative or not trialrows else (0 if trialrows[0]['start']==1 else opening)+sum(r['reported'] for r in trialrows)
  summaries.append(dict(trial=t.trial_id,instruction=t.instruction,answer=result['value'],expected=result['expected'],table_rows=len(trialrows),wrong_rows=len(bad),first_bad=(f"{bad[0]['start']}-{bad[0]['end']}: {bad[0]['reported']} vs {bad[0]['expected']}" if bad else 'not exposed'),reported_rows_recombine=recombined))
out=run.path/'analysis';csvpath=out/'workflow_v1_clean_checkpoint_audit.csv'
with csvpath.open('w') as f:
 writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
lines=['# Workflow v1: clean-case failure review','', 'Reviewed all 100 C responses: 50 workflow and 50 baseline. Repeats share five logs and are not independent questions. Only final response text is available for diagnosis; hidden reasoning is not inferred.','', '| Log | No skill correct/10 | Workflow correct/10 |','|---|---:|---:|']
for wid in sorted(run.manifest['worlds']):
 lines.append(f"| {wid} | {sum(x[0]['correct'] for x in groups[wid,'none'])} | {sum(x[0]['correct'] for x in groups[wid,'workflow_v1'])} |")
lines+=['','## Response behavior','']
for arm in ('none','workflow_v1'):
 items=[x for (w,a),v in groups.items() if a==arm for x in v]
 lines.append(f"- {arm}: {sum(x[0]['correct'] for x in items)}/50 correct; {sum(bool(x[2]) for x in items)}/50 responses expose record-range tables; mean output tokens {statistics.mean(x[1]['usage']['output_tokens'] for x in items):.0f}.")
lines+=['','All 13 workflow failures explicitly recognize that no withdrawals appear. Each exposes a numerical table with at least one source-inconsistent row. Thus those visible tables do not substantiate successful verification. A correct policy statement does not establish correct record selection or arithmetic. The cause of a bad segment total cannot be determined from its numerical offset alone.','', 'The audit compares every parseable range in both arms, including correct answers, with exact C records. It distinguishes segment net changes from cumulative states. It also recombines exposed net rows below: a mismatch with the final answer is a separate visible aggregation inconsistency. Agreement with the final answer does not validate the source-derived rows.','', '| Failed trial | Expected | Answer | Wrong/table rows | First source discrepancy | Opening + exposed net rows |','|---|---:|---:|---:|---|---:|']
for s in sorted(summaries,key=lambda x:x['trial']):lines.append(f"| {s['trial']} | {s['expected']} | {s['answer']} | {s['wrong_rows']}/{s['table_rows']} | {s['first_bad']} | {s['reported_rows_recombine'] if s['reported_rows_recombine'] is not None else 'not applicable'} |")
lines+=['','## Revision hypothesis and limits','', 'V1 places its direct-path instruction after mapping evidence, then still prescribes long-input segments and two separate challenge checks. A candidate can therefore correctly recognize a clean input while performing the elaborate calculation procedure anyway. Workflow v2 moves the task-dependent route before conflict bookkeeping, explicitly skips dependency machinery when irrelevant, and makes segmentation/regrouping optional. It preserves authority, exact revision targets, nested revisions, scope, and operation semantics. It distinguishes source extraction, local calculation, and aggregation in verification.','', 'This is a plausible prompt-level intervention, not proof that tables, length, or extra reasoning caused degradation. Baseline also makes calculation errors, and the arms use different stochastic responses. A new skill-versus-baseline pilot cannot isolate routing from simultaneous wording/length changes or directly estimate v2 minus v1. No instruction contains these log identifiers, numerical answers, or budget-specific rules.','', 'Detailed audit: [workflow_v1_clean_checkpoint_audit.csv](workflow_v1_clean_checkpoint_audit.csv).']
(out/'workflow_v1_clean_failure_review.md').write_text('\n'.join(lines)+'\n')
assert len([s for s in summaries if s['instruction']=='workflow_v1'])==13
assert all(s['wrong_rows']>0 for s in summaries if s['instruction']=='workflow_v1')
print('\n'.join(lines))
