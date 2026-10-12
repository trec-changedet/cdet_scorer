import io
import unittest
from contextlib import redirect_stdout

from cdet_scorer.cli import EvalJig, QuestionEval, DayEval, TopicEval
from cdet_scorer.measures import NumRetrieved, NumRelRet, RelLevel, RBO


class EvalJigTest(unittest.TestCase):
    def test_eval_structures(self):
        q = QuestionEval(qid='q_1')
        q.set_score('num_ret', 10)
        self.assertEqual(q.get_score('num_ret'), 10)
        self.assertIsNone(q.get_score('num_rel'))

        d = DayEval(day='2026-01-01')
        q_eval = d.get_or_create_question('q_1')
        q_eval.set_score('num_ret', 10)
        q2_eval = d.get_or_create_question('q_2')
        q2_eval.set_score('num_ret', 20)

        scores = d.qid_scores_for('num_ret')
        self.assertEqual(scores, {'q_1': 10, 'q_2': 20})

        t = TopicEval(topic='cd2026_001')
        d1 = t.get_or_create_day('2026-01-01')
        d1.get_or_create_question('q_1').set_score('num_ret', 10)
        d2 = t.get_or_create_day('2026-01-02')
        d2.get_or_create_question('q_1').set_score('num_ret', 15)

        self.assertEqual(t.all_qids, {'q_1'})
        day_scores = t.day_scores_for('q_1', 'num_ret')
        self.assertEqual(day_scores, {'2026-01-01': 10, '2026-01-02': 15})

    def test_eval_jig_computation_and_output(self):
        jig = EvalJig(min_rel_level=RelLevel.AWARENESS, max_depth=10)
        jig.add_op(NumRetrieved())
        jig.add_op(NumRelRet())

        qrels_day1_q1 = {'d1': RelLevel.AWARENESS, 'd2': RelLevel.NOT_RELEVANT}
        qrels_day1_q2 = {'d3': RelLevel.AWARENESS}
        qrels_day2_q1 = {'d1': RelLevel.ASSESSMENT}

        jig.compute('cd2026_001', '2026-01-01', 'q_1', ['d1', 'd2', 'd4'], qrels_day1_q1)
        jig.compute('cd2026_001', '2026-01-01', 'q_2', ['d3', 'd5'], qrels_day1_q2)
        jig.compute('cd2026_001', '2026-01-02', 'q_1', ['d1'], qrels_day2_q1)

        # Check stdout of print_scores
        out = io.StringIO()
        with redirect_stdout(out):
            jig.print_scores()
        lines = [line.strip() for line in out.getvalue().strip().split('\n')]
        self.assertIn('cd2026_001 2026-01-01 q_1 num_ret 3', lines)
        self.assertIn('cd2026_001 2026-01-01 q_1 num_rel_ret 1', lines)
        self.assertIn('cd2026_001 2026-01-01 q_2 num_ret 2', lines)
        self.assertIn('cd2026_001 2026-01-01 q_2 num_rel_ret 1', lines)
        self.assertIn('cd2026_001 2026-01-02 q_1 num_ret 1', lines)
        self.assertIn('cd2026_001 2026-01-02 q_1 num_rel_ret 1', lines)

        # Check stdout of print_day_means
        out = io.StringIO()
        with redirect_stdout(out):
            jig.print_day_means()
        day_lines = [line.strip() for line in out.getvalue().strip().split('\n')]
        # num_ret reduce is sum: day1 has q_1 (3) + q_2 (2) = 5
        self.assertIn('cd2026_001 2026-01-01 all num_ret 5', day_lines)
        self.assertIn('cd2026_001 2026-01-01 all num_rel_ret 2', day_lines)
        self.assertIn('cd2026_001 2026-01-02 all num_ret 1', day_lines)
        self.assertIn('cd2026_001 2026-01-02 all num_rel_ret 1', day_lines)

        # Check stdout of print_qid_means
        out = io.StringIO()
        with redirect_stdout(out):
            jig.print_qid_means()
        qid_lines = [line.strip() for line in out.getvalue().strip().split('\n')]
        # num_ret reduce for q_1 across day1 (3) and day2 (1) = 4
        self.assertIn('cd2026_001 all q_1 num_ret 4', qid_lines)
        self.assertIn('cd2026_001 all q_1 num_rel_ret 2', qid_lines)
        self.assertIn('cd2026_001 all q_2 num_ret 2', qid_lines)
        self.assertIn('cd2026_001 all q_2 num_rel_ret 1', qid_lines)

    def test_question_ranking_evaluation(self):
        jig = EvalJig()
        jig.add_op(RBO(p=0.8))

        jig.compute_qranking('cd2026_001', '2026-01-01', ['q1', 'q2'], ['q1', 'q2'])
        jig.compute_qranking('cd2026_001', '2026-01-02', ['q1', 'q2'], ['q2', 'q1'])

        out = io.StringIO()
        with redirect_stdout(out):
            jig.print_qranking_scores()
        lines = [line.strip() for line in out.getvalue().strip().split('\n')]
        self.assertIn("cd2026_001 2026-01-01 qranking rbo(p=0.8) 1.0000", lines)
        self.assertIn("cd2026_001 2026-01-02 qranking rbo(p=0.8) 0.8000", lines)

        out = io.StringIO()
        with redirect_stdout(out):
            jig.print_qranking_means()
        mean_lines = [line.strip() for line in out.getvalue().strip().split('\n')]
        self.assertIn("cd2026_001 all qranking rbo(p=0.8) 0.9000", mean_lines)


if __name__ == '__main__':
    unittest.main()
