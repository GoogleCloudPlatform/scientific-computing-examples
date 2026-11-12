import json
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canary_capacity_check import CanaryCapacityChecker

class TestCanaryCapacityCheck(unittest.TestCase):

    def test_canary_vm_success_and_rapid_deletion(self):
        executed_commands = []

        def mock_runner(cmd):
            executed_commands.append(cmd)
            # Both create and delete succeed
            return 0, '{"id": "12345", "status": "RUNNING"}', ""

        checker = CanaryCapacityChecker(
            project_id="test-proj",
            region="us-central1",
            command_runner=mock_runner,
        )

        res = checker.test_single_vm(
            zone="us-central1-a",
            machine_type="c4-standard-192",
            boot_disk_type="hyperdisk-balanced",
            boot_disk_size_gb=100,
            delete_delay_sec=0,  # no sleep in test
        )

        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["cleanup_status"], "DELETED_RAPIDLY")
        self.assertEqual(len(executed_commands), 2)

        create_cmd = " ".join(executed_commands[0])
        self.assertIn("compute instances create", create_cmd)
        self.assertIn("--machine-type=c4-standard-192", create_cmd)
        self.assertIn("--boot-disk-type=hyperdisk-balanced", create_cmd)
        self.assertIn("--zone=us-central1-a", create_cmd)

        delete_cmd = " ".join(executed_commands[1])
        self.assertIn("compute instances delete", delete_cmd)
        self.assertIn("--zone=us-central1-a", delete_cmd)
        self.assertIn(res["vm_name"], delete_cmd)

    def test_canary_vm_stockout_detection(self):
        executed_commands = []

        def mock_runner(cmd):
            executed_commands.append(cmd)
            error_msg = "ERROR: (gcloud.compute.instances.create) The zone 'projects/test-proj/zones/us-central1-a' does not have enough resources available to fulfill the request. (ZONE_RESOURCE_POOL_EXHAUSTED)"
            return 1, "", error_msg

        checker = CanaryCapacityChecker(
            project_id="test-proj",
            region="us-central1",
            command_runner=mock_runner,
        )

        res = checker.test_single_vm(
            zone="us-central1-a",
            machine_type="h4d-standard-192",
            delete_delay_sec=0,
        )

        self.assertEqual(res["status"], "STOCKOUT")
        self.assertEqual(res["cleanup_status"], "NOT_APPLICABLE")
        # Ensure delete was not called since creation failed
        self.assertEqual(len(executed_commands), 1)

    def test_canary_vm_quota_exceeded_detection(self):
        def mock_runner(cmd):
            error_msg = "ERROR: (gcloud.compute.instances.create) Quota 'CPUS' exceeded. Limit: 100.0 in region us-central1. (QUOTA_EXCEEDED)"
            return 1, "", error_msg

        checker = CanaryCapacityChecker(
            project_id="test-proj",
            region="us-central1",
            command_runner=mock_runner,
        )

        res = checker.test_single_vm(
            zone="us-central1-a",
            machine_type="c3-standard-88",
            delete_delay_sec=0,
        )

        self.assertEqual(res["status"], "QUOTA_EXCEEDED")

    def test_quota_headroom_computation_and_storage_constraint(self):
        checker = CanaryCapacityChecker(
            project_id="test-proj",
            region="us-central1",
        )

        # Standard CPU headroom allows 10 instances (1920 CPUs / 192 = 10 instances).
        # But Hyperdisk headroom is only 500 GB (500 GB / 100 GB = 5 instances).
        # Storage quota should constrain max VMs to 5 and trigger warning.
        raw_quotas = {
            "CPUS": {"limit": 2000.0, "usage": 80.0, "headroom": 1920.0},
            "PREEMPTIBLE_CPUS": {"limit": 4000.0, "usage": 160.0, "headroom": 3840.0},
            "SSD_TOTAL_GB": {"limit": 50000.0, "usage": 10000.0, "headroom": 40000.0},
            "HYPERDISK_BALANCED_TOTAL_CAPACITY_GB": {"limit": 1000.0, "usage": 500.0, "headroom": 500.0},
        }

        analysis = checker.compute_quota_headroom(
            raw_quotas=raw_quotas,
            target_machine_type="c4-standard-192",
            vcpus_per_vm=192,
            boot_disk_gb=100,
            scratch_disk_gb=0,
        )

        self.assertEqual(analysis["max_vms_standard_cpu"], 10)
        self.assertEqual(analysis["max_vms_spot_cpu"], 20)
        self.assertEqual(analysis["storage_headroom_gb"], 500.0)
        self.assertEqual(analysis["max_vms_storage"], 5)
        self.assertTrue(analysis["is_storage_constrained"])

        report = checker.generate_report(canary_results=[], quota_analysis=analysis)
        self.assertIn("Storage Quota Bottleneck Detected", report)
        self.assertIn("constrains your deployment to a maximum of **5 instances**", report)
        self.assertIn("Standard CPU quota permits **10 instances**", report)

    def test_quota_headroom_unconstrained(self):
        checker = CanaryCapacityChecker(
            project_id="test-proj",
            region="us-central1",
        )

        raw_quotas = {
            "CPUS": {"limit": 1000.0, "usage": 232.0, "headroom": 768.0},  # 768 / 192 = 4 VMs
            "PREEMPTIBLE_CPUS": {"limit": 2000.0, "usage": 0.0, "headroom": 2000.0},
            "SSD_TOTAL_GB": {"limit": 50000.0, "usage": 10000.0, "headroom": 40000.0},
            "HYPERDISK_BALANCED_TOTAL_CAPACITY_GB": {"limit": 5000.0, "usage": 1000.0, "headroom": 4000.0}, # 4000 / 100 = 40 VMs
        }

        analysis = checker.compute_quota_headroom(
            raw_quotas=raw_quotas,
            target_machine_type="c4-standard-192",
            vcpus_per_vm=192,
            boot_disk_gb=100,
            scratch_disk_gb=0,
        )

        self.assertEqual(analysis["max_vms_standard_cpu"], 4)
        self.assertEqual(analysis["max_vms_storage"], 40)
        self.assertFalse(analysis["is_storage_constrained"])

        report = checker.generate_report(canary_results=[], quota_analysis=analysis)
        self.assertNotIn("Storage Quota Bottleneck Detected", report)
        self.assertIn("Storage OK", report)
        self.assertIn("Filestore Capacity Headroom", report)
        self.assertIn("Managed Lustre Scratch Headroom", report)

    def test_quota_headroom_filestore_calculation(self):
        checker = CanaryCapacityChecker(
            project_id="test-proj",
            region="us-central1",
        )

        raw_quotas = {
            "CPUS": {"limit": 1000.0, "usage": 0.0, "headroom": 1000.0},
            "PREEMPTIBLE_CPUS": {"limit": 1000.0, "usage": 0.0, "headroom": 1000.0},
            "SSD_TOTAL_GB": {"limit": 50000.0, "usage": 0.0, "headroom": 50000.0},
            "HYPERDISK_BALANCED_TOTAL_CAPACITY_GB": {"limit": 5000.0, "usage": 0.0, "headroom": 5000.0},
            "FILESTORE_TIER_HIGH_SCALE_SSD_TOTAL_CAPACITY_GB": {"limit": 204800.0, "usage": 0.0, "headroom": 204800.0},
        }

        analysis = checker.compute_quota_headroom(raw_quotas=raw_quotas)
        # 204800 GB / 1024 = 200.0 TB
        self.assertEqual(analysis["filestore_headroom_tb"], 200.0)
        self.assertEqual(analysis["lustre_headroom_tb"], 500.0)

        report = checker.generate_report(canary_results=[], quota_analysis=analysis)
        self.assertIn("200 TB", report)
        self.assertIn("500 TB", report)

if __name__ == "__main__":
    unittest.main()
