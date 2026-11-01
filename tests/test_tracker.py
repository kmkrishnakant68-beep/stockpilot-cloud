import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import stockpilot_ma_tracker as tracker

NOW = datetime(2026, 10, 31, 0, 9, tzinfo=timezone.utc)


def result(symbol='AMD', day='2026-10-30', price=90, prior=None):
    history = pd.DataFrame({'Close': [100.] * 200 + [price]},
                           index=pd.date_range(end=day, periods=201))
    return tracker.moving_average_result(symbol, history, None, NOW, prior)


class TrackerTests(unittest.TestCase):
    def test_downward_only_and_repeat(self):
        first = result(prior={'below50': False, 'below200': False})
        self.assertTrue(first['crossed_below50'])
        self.assertTrue(first['crossed_below200'])
        repeat = result(prior=tracker.observation_state(first))
        self.assertFalse(repeat['crossed_below50'])
        recovery = result(price=110, prior=tracker.observation_state(first))
        self.assertFalse(recovery['below50'])
        self.assertFalse(recovery['crossed_below50'])

    def test_stale_rejected_before_crossing(self):
        for symbol, window in [('AMD', 50), ('VOO', 50), ('ASML', 200)]:
            with self.subTest(symbol=symbol):
                prior = tracker.observation_state(result(symbol))
                self.assertTrue(prior[f'below{window}'])
                with self.assertRaisesRegex(ValueError, 'Stale observation'):
                    result(symbol, '2026-10-29', 110, prior)

    def test_completed_close_cannot_be_replaced_by_quote(self):
        with self.assertRaisesRegex(ValueError, 'provisional'):
            tracker.validate_observation(
                {'as_of_date': '2026-10-30', 'price_mode': 'indicative session quote (may be delayed)'},
                tracker.observation_state(result()))

    def test_first_scan_uses_previous_bar(self):
        self.assertTrue(result()['crossed_below50'])

    def test_all_stale_preserves_every_file_and_legacy_state(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            old = result()
            tracker.save_json(output / 'latest_signals.json', {'stocks': [old]})
            tracker.save_json(output / 'state.json', {'AMD': {'below50': True, 'below200': True}})
            tracker.save_json(output / 'new_alerts.json', {'alerts': []})
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            with patch.object(tracker, 'fetch_and_analyze', return_value=result(day='2026-10-29', price=110)):
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                    tracker.run_once(['AMD'], output)
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_partial_stale_retains_snapshot_and_no_false_recross(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            old = result(prior={'below50': True, 'below200': True})
            tracker.save_json(output / 'latest_signals.json', {'stocks': [old]})
            tracker.save_json(output / 'state.json', {'AMD': {'below50': True, 'below200': True}})
            def fetch(symbol, now, prior):
                return result(symbol, '2026-10-29', 110) if symbol == 'AMD' else result(symbol, price=110)
            with patch.object(tracker, 'fetch_and_analyze', side_effect=fetch), contextlib.redirect_stdout(io.StringIO()):
                tracker.run_once(['AMD', 'VOO'], output)
            state = json.loads((output / 'state.json').read_text())
            self.assertEqual(state['AMD']['as_of_date'], '2026-10-30')
            self.assertTrue(state['AMD']['below50'])
            retained = json.loads((output / 'latest_signals.json').read_text())['stocks'][0]
            self.assertEqual(retained['price'], old['price'])
            self.assertIn('Stale observation', retained['refresh_error'])
            self.assertEqual(json.loads((output / 'new_alerts.json').read_text())['alerts'], [])
            self.assertFalse(result(prior=state['AMD'])['crossed_below50'])


if __name__ == '__main__':
    unittest.main()
