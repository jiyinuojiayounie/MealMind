import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dev_manager as manager


class DevelopmentManagerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        state = patch.object(manager, "STATE", Path(self.directory.name))
        state.start()
        self.addCleanup(state.stop)

    def test_unverified_record_is_left_untouched_even_if_group_exists(self):
        record = manager.metadata("backend")
        record.write_text(json.dumps({"pid": 300, "token": "a" * 48}))
        with (
            patch.object(manager.os, "getpgid", return_value=300),
            patch.object(manager, "group_members", return_value={300, 301}),
            patch.object(manager.socket.socket, "connect", side_effect=ConnectionRefusedError),
            patch.object(manager.os, "killpg") as signal_group,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertFalse(manager.stop(["backend"]))
        signal_group.assert_not_called()
        self.assertTrue(record.exists())
        self.assertIn("unverified", output.getvalue())

    def test_dead_or_malformed_metadata_can_be_removed_without_signaling(self):
        record = manager.metadata("backend")
        for contents in ('{"pid": 300, "token": "' + "a" * 48 + '"}', "malformed"):
            with self.subTest(contents=contents):
                record.write_text(contents)
                with (
                    patch.object(manager.os, "getpgid", side_effect=ProcessLookupError),
                    patch.object(manager, "group_members", return_value=set()),
                    patch.object(manager.os, "killpg") as signal_group,
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    self.assertTrue(manager.stop(["backend"]))
                signal_group.assert_not_called()
                self.assertFalse(record.exists())

    def test_unmanaged_listeners_block_preflight(self):
        with (
            patch.object(manager, "listeners", return_value={300: "node"}),
            patch.object(manager.os, "killpg") as signal_group,
            self.assertRaisesRegex(manager.DevError, "occupied by PID 300"),
        ):
            manager.preflight()
        signal_group.assert_not_called()

    def test_logs_only_emit_fixed_messages(self):
        worker_output = io.BytesIO(b"Traceback API_KEY=fixture-secret\n"
                                   b"private database content\n"
                                   b"error fixture-secret repeated\n"
                                   b"Vite ready in 24ms fixture-secret\n")
        with contextlib.redirect_stdout(io.StringIO()) as output:
            manager.filter_output(worker_output)
        self.assertEqual(output.getvalue().splitlines(), [
            "Service reported an error; private details withheld.",
            "Vite reported startup complete.",
        ])


if __name__ == "__main__":
    unittest.main()
