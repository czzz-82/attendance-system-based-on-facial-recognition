import unittest
from unittest.mock import patch

from app import create_app


class AttendanceVerifyModelLivenessTests(unittest.TestCase):
    def setUp(self):
        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["uid"] = 1
            session["username"] = "teacher"
            session["role"] = "teacher"

    def test_verify_blocks_when_model_detects_spoof(self):
        with patch("app.routes.api_attendance.liveness.get_session") as get_session, \
             patch("app.routes.api_attendance.liveness.consume_session"), \
             patch("app.routes.api_attendance.liveness.verify_action", return_value=True), \
             patch("app.routes.api_attendance.face_engine.decode_dataurl", return_value=object()), \
             patch("app.routes.api_attendance.liveness.measure_frame") as measure_frame, \
             patch("app.routes.api_attendance.liveness_model.verify_liveness_from_frames") as verify_model, \
             patch("app.routes.api_attendance.execute"):
            get_session.return_value = type("Sess", (), {"used": False, "challenges": ["blink"]})()
            measure_frame.return_value = type("Metric", (), {"has_face": True})()
            verify_model.return_value = {
                "checked": True,
                "available": True,
                "passed": False,
                "score": 0.2,
                "reason": "spoof_detected",
                "frame_count": 3,
            }

            response = self.client.post("/api/attendance/verify", json={"token": "t", "frames": ["a"] * 8})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "fail")
        self.assertFalse(payload["model_liveness_passed"])
        self.assertEqual(payload["model_liveness_reason"], "spoof_detected")

    def test_verify_allows_success_when_model_is_skipped(self):
        fake_face = type("FaceRect", (), {"width": lambda self: 100, "height": lambda self: 120})()
        with patch("app.routes.api_attendance.liveness.get_session") as get_session, \
             patch("app.routes.api_attendance.liveness.consume_session"), \
             patch("app.routes.api_attendance.liveness.verify_action", return_value=True), \
             patch("app.routes.api_attendance.face_engine.decode_dataurl", return_value=object()), \
             patch("app.routes.api_attendance.liveness.measure_frame") as measure_frame, \
             patch("app.routes.api_attendance.liveness_model.verify_liveness_from_frames") as verify_model, \
             patch("app.routes.api_attendance.face_engine.detect_faces", return_value=[fake_face]), \
             patch("app.routes.api_attendance.face_engine.encode_face_with_enhancement", return_value=object()), \
             patch("app.routes.api_attendance.query_all", return_value=[]), \
             patch("app.routes.api_attendance.face_engine.match_one", return_value=(1, 0.2)), \
             patch("app.routes.api_attendance.query_one", return_value={
                 "id": 1,
                 "student_no": "2024001",
                 "name": "Alice",
                 "class_name": "CS1",
                 "photo_path": "a.jpg",
             }), \
             patch("app.routes.api_attendance.face_engine.crop_face", return_value=object()), \
             patch("app.routes.api_attendance.face_engine.analyze_emotion", return_value="happy"), \
             patch("app.routes.api_attendance.execute"):
            get_session.return_value = type("Sess", (), {"used": False, "challenges": ["blink"]})()
            measure_frame.return_value = type("Metric", (), {"has_face": True})()
            verify_model.return_value = {
                "checked": False,
                "available": False,
                "passed": None,
                "score": None,
                "reason": "dependency_missing",
                "frame_count": 0,
            }

            response = self.client.post("/api/attendance/verify", json={"token": "t", "frames": ["a"] * 8})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "success")
        self.assertFalse(payload["model_liveness_checked"])
        self.assertEqual(payload["model_liveness_reason"], "dependency_missing")

    def test_verify_note_contains_model_liveness_summary(self):
        fake_face = type("FaceRect", (), {"width": lambda self: 100, "height": lambda self: 120})()
        with patch("app.routes.api_attendance.liveness.get_session") as get_session, \
             patch("app.routes.api_attendance.liveness.consume_session"), \
             patch("app.routes.api_attendance.liveness.verify_action", return_value=True), \
             patch("app.routes.api_attendance.face_engine.decode_dataurl", return_value=object()), \
             patch("app.routes.api_attendance.liveness.measure_frame", return_value=type("Metric", (), {"has_face": True})()), \
             patch("app.routes.api_attendance.liveness_model.verify_liveness_from_frames", return_value={
                 "checked": True,
                 "available": True,
                 "passed": True,
                 "score": 0.82,
                 "reason": "passed",
                 "frame_count": 5,
             }), \
             patch("app.routes.api_attendance.face_engine.detect_faces", return_value=[fake_face]), \
             patch("app.routes.api_attendance.face_engine.encode_face_with_enhancement", return_value=object()), \
             patch("app.routes.api_attendance.query_all", return_value=[]), \
             patch("app.routes.api_attendance.face_engine.match_one", return_value=(None, 0.8)), \
             patch("app.routes.api_attendance.query_one", return_value=None), \
             patch("app.routes.api_attendance.face_engine.crop_face", return_value=object()), \
             patch("app.routes.api_attendance.face_engine.analyze_emotion", return_value="happy"), \
             patch("app.routes.api_attendance.execute") as execute_mock:
            get_session.return_value = type("Sess", (), {"used": False, "challenges": ["blink"]})()
            self.client.post("/api/attendance/verify", json={"token": "t", "frames": ["a"] * 8})

        note = execute_mock.call_args[0][1][-1]
        self.assertIn("model_liveness=passed", note)
        self.assertIn("score=0.82", note)


if __name__ == "__main__":
    unittest.main()
