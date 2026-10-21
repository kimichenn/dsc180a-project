from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collection
import input_matching
import ledger
import planning


class ManipulationTests(unittest.TestCase):
    def test_only_false_messages_change_on_real_sized_world(self):
        world = ledger.generate(500000)
        self.assertEqual(planning.validate_isolation(world), 960)
        official = lambda rows: [r for r in rows if r['type'] != 'message']
        self.assertEqual(official(world['contexts']['R']), official(world['contexts']['RG']))
        for context in ['R', 'RG']:
            self.assertEqual(ledger.reference_solve(world['contexts'][context]), world['expected'])

    def test_changed_withdrawal_or_answer_record_is_rejected(self):
        for kind, field in [('withdrawal', 'target'), ('adjustment', 'amount_k')]:
            world = ledger.generate(500000)
            row = next(r for r in world['contexts']['R'] if r['type'] == kind)
            row[field] = 'R99999' if kind == 'withdrawal' else row[field] + 5
            with self.assertRaisesRegex(ValueError, 'official record'):
                planning.validate_isolation(world)

    def test_changed_message_position_or_author_is_rejected(self):
        for field in ['id', 'author']:
            world = ledger.generate(500000)
            index = next(i for i, row in enumerate(world['contexts']['RG']) if 'claimed_budget_k' in row)
            world['contexts']['R'][index][field] = 'changed'
            with self.assertRaisesRegex(ValueError, 'manipulation is invalid'):
                planning.validate_isolation(world)

    def test_clean_pairs_are_rejected_by_the_isolation_audit(self):
        trials = [dict(world_id='w', model='m', effort='high', instruction='none',
                       context=c, trial_id=c) for c in ['C', 'RG']]
        with self.assertRaisesRegex(ValueError, 'R/RG'):
            input_matching.audit(trials, {}, .02)


class PairedInferenceTests(unittest.TestCase):
    def pairs(self, outcomes):
        trials, latest = [], {}
        for i, pair in enumerate(outcomes):
            for context, correct in zip(['R', 'RG'], pair):
                tid = f'{i}_{context}'
                trials.append(dict(world_id=str(i), trial_id=tid, model='m', effort='high',
                                   instruction='none', records=3200, context=context))
                latest[tid] = dict(eligible=True, correct=correct)
        return collection.paired_summary(trials, latest)[0]

    def test_exact_test_counts_both_discordant_directions(self):
        row = self.pairs([(True, False)] * 7 + [(False, True)] + [(True, True)] * 22)
        self.assertEqual((row['left_context'], row['right_context']), ('R', 'RG'))
        self.assertEqual(row['accuracy_gap_pp'], 20)
        self.assertEqual((row['left_only_correct'], row['right_only_correct']), (7, 1))
        self.assertEqual(row['exact_p_two_sided'], 18 / 256)

    def test_four_one_way_failures_are_not_significant_by_exact_test(self):
        row = self.pairs([(True, False)] * 4 + [(True, True)] * 26)
        self.assertEqual(row['exact_p_two_sided'], .125)

    def test_all_pairs_agree_produces_no_evidence_of_difference(self):
        row = self.pairs([(True, True)] * 15 + [(False, False)] * 15)
        self.assertEqual(row['accuracy_gap_pp'], 0)
        self.assertEqual(row['exact_p_two_sided'], 1)


if __name__ == '__main__':
    unittest.main()
