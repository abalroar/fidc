import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.refresh_all_documentary_diligence import (
    RefreshConfig, RefreshLockedError, ResourceFloorError, exclusive_refresh_lock,
    run_refresh, stage_command, documented_additional_cnpjs,
)


class DocumentaryRefreshOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cnpj = "63953620000165"
        (self.root / "portfolios.json").write_text(json.dumps({"portfolios": [{"id": "A", "funds": [{"cnpj": self.cnpj}]}]}))
        (self.root / "scripts").mkdir()
        (self.root / "scripts/refresh_documentary_ime.py").write_text("# --offline-reprocess\n")
        self.config = RefreshConfig(self.root, disk_floor_gb=0, through="09/2026")

    def tearDown(self):
        self.temporary.cleanup()

    def create_fund(self):
        directory = self.root / "data/documentary_diligence/funds"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{self.cnpj}.json").write_text(json.dumps({"schema_version": 2, "cnpj": self.cnpj, "criteria": []}))

    def runner(self, calls, fail_once=None):
        def run(command, **kwargs):
            calls.append(command)
            if "build_documentary_diligence.py" in command[1]:
                self.create_fund()
            failed = fail_once and any(fail_once in token for token in command)
            return {"returncode": 9 if failed else 0, "peak_children_rss_bytes": 12345}
        return run

    def test_full_stages_are_serial_and_build_is_fresh(self):
        calls=[]
        status=run_refresh(self.config, runner=self.runner(calls))
        self.assertEqual(7,len(calls))
        self.assertEqual(["refresh_documentary_corpus.py","refresh_documentary_corpus.py","refresh_documentary_quarterly.py","refresh_documentary_quarterly.py","refresh_documentary_ime.py","build_documentary_diligence.py","report_documentary_diligence.py"], [Path(c[1]).name for c in calls])
        self.assertNotIn("--resume",calls[5])
        self.assertIn("current",calls[0]);self.assertIn("history",calls[1])
        self.assertEqual("COMPLETE",status["state"])
        self.assertEqual(1,status["verification"]["generated_valid"])
        self.assertEqual(12345,status["peak_children_rss_bytes"])

    def test_exclusive_lock_rejects_second_wrapper(self):
        base=self.root/"data/documentary_diligence"
        with exclusive_refresh_lock(base):
            with self.assertRaises(RefreshLockedError):
                with exclusive_refresh_lock(base):pass

    def test_failure_resumes_failed_stage_without_repeating_completed(self):
        calls=[]
        with self.assertRaises(RuntimeError):run_refresh(self.config,runner=self.runner(calls,fail_once="history"))
        state=json.loads((self.root/"data/documentary_diligence/run_status.json").read_text())
        self.assertEqual("ERROR",state["state"]);self.assertEqual("COMPLETE",state["stages"]["current"]["state"])
        calls=[];status=run_refresh(self.config,runner=self.runner(calls))
        self.assertEqual(6,len(calls));self.assertIn("history",calls[0]);self.assertEqual("COMPLETE",status["state"])

    def test_offline_mode_indexes_locally_and_does_not_fetch_history_or_ime(self):
        self.config.skip_network=True;calls=[]
        status=run_refresh(self.config,runner=self.runner(calls))
        self.assertIn("--local-only",calls[0]);self.assertNotIn("--network",calls[0])
        self.assertIn("--offline-reprocess",calls[1]);self.assertIn("--offline-reprocess",calls[2])
        self.assertEqual("SKIPPED_NETWORK",status["stages"]["history"]["state"])
        self.assertEqual("PARTIAL_COMPLETE",status["state"])

    def test_budget_is_shared_between_pdf_passes(self):
        calls=[]
        with patch("scripts.refresh_all_documentary_diligence.stage_downloaded_bytes",side_effect=[1024**3,0,1024**2,0]):
            status=run_refresh(self.config,runner=self.runner(calls))
        self.assertEqual("5.0",calls[1][calls[1].index("--max-download-gb")+1])
        self.assertEqual(1024**3,status["downloaded_pdf_bytes"])
        self.assertEqual(1024**2,status["downloaded_quarterly_bytes"])
        self.assertEqual(str(.25-1/1024),calls[3][calls[3].index("--max-download-gb")+1])

    def test_disk_floor_stops_without_running_a_child(self):
        calls=[];self.config.disk_floor_gb=10
        with patch("scripts.refresh_all_documentary_diligence.shutil.disk_usage") as usage:
            usage.return_value.free=1
            with self.assertRaises(ResourceFloorError):run_refresh(self.config,runner=self.runner(calls))
        self.assertEqual([],calls)
        self.assertEqual("RESOURCE_LIMIT",json.loads((self.root/"data/documentary_diligence/run_status.json").read_text())["state"])

    def test_complete_requires_every_registered_fund(self):
        def runner(command,**kwargs):return {"returncode":0}
        with self.assertRaisesRegex(RuntimeError,"Escopo gerado incompleto"):
            run_refresh(self.config,runner=runner)

    def test_selected_stage_marks_partial_scope_and_never_schedules(self):
        self.config.only_stage=("report",);calls=[]
        status=run_refresh(self.config,runner=self.runner(calls))
        self.assertEqual(1,len(calls));self.assertEqual("PARTIAL_COMPLETE",status["state"])
        self.assertEqual("selected_stages_only",status["scope"])

    def test_only_sourced_reviewed_relationships_expand_scope(self):
        directory=self.root/"data/documentary_diligence/verified_overrides";directory.mkdir(parents=True)
        sourced={"cnpj":"41970012000126","relationship":"named_investee","sources":[{"document_id":123456,"reference_date":"2026-10-13","page":11}]}
        candidate={"cnpj":"30035329000159","relationship":"candidate_requires_primary_validation","sources":sourced["sources"]}
        (directory/f"{self.cnpj}.json").write_text(json.dumps({"lookthrough":[sourced,candidate]}))
        self.assertEqual(["41970012000126"],documented_additional_cnpjs(self.root,{self.cnpj}))

    def test_quarterly_budget_checkpoint_still_builds_and_reports(self):
        calls=[];normal=self.runner(calls)
        def runner(command,**kwargs):
            if 'refresh_documentary_quarterly.py' in command[1] and 'history' in command:
                calls.append(command)
                path=self.root/'data/documentary_diligence/quarterly_index.json'
                path.write_text(json.dumps({'stopped_reason':'download_budget_reached','acquisition_pass':'history','downloaded_bytes_this_run':1000}))
                return {'returncode':2}
            return normal(command,**kwargs)
        status=run_refresh(self.config,runner=runner)
        self.assertEqual('COMPLETE_WITH_RESOURCE_LIMITS',status['state'])
        self.assertEqual('RESOURCE_LIMIT',status['stages']['quarterly_history']['state'])
        self.assertEqual('report_documentary_diligence.py',Path(calls[-1][1]).name)

    def test_interrupted_child_bytes_reduce_resumed_budget(self):
        self.config.only_stage=('current',)
        def interrupted(command,**kwargs):
            corpus=self.root/'data/documentary_diligence/corpus';corpus.mkdir(parents=True)
            (corpus/f'{self.cnpj}.json').write_text(json.dumps({'mode':'network','acquisition_pass':'current',
                                                             'downloaded_bytes_this_run':2*1024**3}))
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):run_refresh(self.config,runner=interrupted)
        state=json.loads((self.root/'data/documentary_diligence/run_status.json').read_text())
        self.assertEqual('ERROR',state['state']);self.assertEqual(0,state['downloaded_pdf_bytes'])
        calls=[]
        status=run_refresh(self.config,runner=self.runner(calls))
        self.assertEqual('4.0',calls[0][calls[0].index('--max-download-gb')+1])
        self.assertEqual(2*1024**3,status['downloaded_pdf_bytes'])

    def test_ocr_stage_requires_explicit_flag_and_runs_before_build(self):
        self.config.recover_unreadable_text=True;calls=[]
        status=run_refresh(self.config,runner=self.runner(calls))
        self.assertEqual(8,len(calls));self.assertEqual('recover_documentary_ocr.py',Path(calls[5][1]).name)
        self.assertEqual('build_documentary_diligence.py',Path(calls[6][1]).name)
        self.assertEqual('COMPLETE',status['state']);self.assertIn('--max-pages',calls[5])
        self.config.recover_unreadable_text=False;self.config.only_stage=('ocr',)
        with self.assertRaisesRegex(ValueError,'recover-unreadable-text'):run_refresh(self.config,runner=self.runner([]))

    def test_optional_ocr_page_limit_keeps_build_and_report_with_explicit_state(self):
        self.config.recover_unreadable_text=True;calls=[];normal=self.runner(calls)
        def runner(command,**kwargs):
            if 'recover_documentary_ocr.py' in command[1]:
                calls.append(command);qa=self.root/'data/documentary_diligence/qa';qa.mkdir(parents=True)
                (qa/'ocr_recovery.json').write_text(json.dumps({'state':'resource_limit','stopped_reason':'page_budget_reached; document not truncated'}))
                return {'returncode':2}
            return normal(command,**kwargs)
        status=run_refresh(self.config,runner=runner)
        self.assertEqual('COMPLETE_WITH_RESOURCE_LIMITS',status['state'])
        self.assertEqual('RESOURCE_LIMIT',status['stages']['ocr']['state'])
        self.assertEqual('report_documentary_diligence.py',Path(calls[-1][1]).name)


if __name__=="__main__":unittest.main()
