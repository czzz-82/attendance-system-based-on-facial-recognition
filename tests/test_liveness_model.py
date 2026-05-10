import unittest
from unittest.mock import patch

from app import liveness_model


class LivenessModelDecisionTests(unittest.TestCase):
    def test_aggregate_scores_passes_when_average_meets_threshold(self):
        result = liveness_model.build_result_from_scores(
            scores=[0.9, 0.7, 0.6],
            threshold=0.5,
        )

        self.assertTrue(result["checked"])
        self.assertTrue(result["available"])
        self.assertTrue(result["passed"])
        self.assertAlmostEqual(result["score"], 0.7333, places=4)
        self.assertEqual(result["reason"], "passed")

    def test_aggregate_scores_fails_when_average_below_threshold(self):
        result = liveness_model.build_result_from_scores(
            scores=[0.1, 0.3, 0.4],
            threshold=0.5,
        )

        self.assertTrue(result["checked"])
        self.assertTrue(result["available"])
        self.assertFalse(result["passed"])
        self.assertAlmostEqual(result["score"], 0.2667, places=4)
        self.assertEqual(result["reason"], "spoof_detected")

    def test_skip_result_marks_model_unchecked(self):
        result = liveness_model.build_skip_result("dependency_missing")

        self.assertFalse(result["checked"])
        self.assertFalse(result["available"])
        self.assertIsNone(result["passed"])
        self.assertIsNone(result["score"])
        self.assertEqual(result["reason"], "dependency_missing")


class LivenessModelSamplingTests(unittest.TestCase):
    def test_pick_frame_indices_returns_evenly_spaced_positions(self):
        self.assertEqual(
            liveness_model.pick_frame_indices(list(range(10)), target_count=5),
            [0, 2, 4, 7, 9],
        )

    def test_pick_frame_indices_returns_all_when_shorter_than_target(self):
        self.assertEqual(
            liveness_model.pick_frame_indices([1, 3, 5], target_count=5),
            [1, 3, 5],
        )

    def test_pick_frame_indices_returns_empty_for_no_candidates(self):
        self.assertEqual(
            liveness_model.pick_frame_indices([], target_count=5),
            [],
        )


class LivenessModelVerificationTests(unittest.TestCase):
    def test_verify_returns_skip_when_no_face_frames(self):
        result = liveness_model.verify_liveness_from_frames(
            decoded_frames=[object(), object()],
            metrics=[type("Metric", (), {"has_face": False})(), type("Metric", (), {"has_face": False})()],
        )

        self.assertFalse(result["checked"])
        self.assertEqual(result["reason"], "no_face_frames")

    @patch("app.liveness_model.score_frame", side_effect=[0.9, 0.7, 0.8])
    @patch("app.liveness_model.pick_face_frame_indices", return_value=[0, 1, 2])
    def test_verify_aggregates_scores_from_sampled_frames(self, _pick, _score):
        result = liveness_model.verify_liveness_from_frames(
            decoded_frames=[object(), object(), object()],
            metrics=[type("Metric", (), {"has_face": True})() for _ in range(3)],
        )

        self.assertTrue(result["checked"])
        self.assertTrue(result["passed"])
        self.assertAlmostEqual(result["score"], 0.8, places=4)


if __name__ == "__main__":
    unittest.main()
