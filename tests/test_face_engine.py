import importlib
import unittest


class FaceEngineInitializationTests(unittest.TestCase):
    def test_get_detector_initializes_without_scope_error(self):
        face_engine = importlib.import_module("app.face_engine")
        face_engine = importlib.reload(face_engine)

        detector = face_engine.get_detector()

        self.assertIsNotNone(detector)


if __name__ == "__main__":
    unittest.main()
