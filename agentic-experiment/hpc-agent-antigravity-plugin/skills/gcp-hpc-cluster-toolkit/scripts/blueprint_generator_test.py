import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from blueprint_generator import generate_blueprint, generate_batch_flexibility_policy, MACHINE_SPECS

class TestBlueprintGenerator(unittest.TestCase):
    def test_h3_generation(self):
        bp = generate_blueprint(
            project_id="test-proj",
            region="us-central1",
            zone="us-central1-a",
            cluster_name="test-cluster",
            compute_family="h3",
            max_nodes=16,
            storage_type="filestore-high-scale",
            enable_compact_placement=True,
            enable_spot=False,
        )
        self.assertEqual(bp["blueprint_name"], "test-cluster")
        modules = bp["spec"]["deployment_groups"][0]["modules"]
        comp = next(m for m in modules if m["id"] == "compute_partition")
        self.assertEqual(comp["settings"]["boot_disk_type"], "hyperdisk-balanced")
        self.assertEqual(comp["settings"]["bandwidth_tier"], "TIER_1")
        self.assertTrue(any(m["id"] == "placement_group" for m in modules))

    def test_gen4_c4_generation(self):
        bp = generate_blueprint(
            project_id="test-proj",
            region="us-central1",
            zone="us-central1-a",
            cluster_name="c4-cluster",
            compute_family="c4",
            max_nodes=32,
            storage_type="filestore-high-scale",
            enable_compact_placement=True,
            enable_spot=False,
            hyperdisk_scratch_gb=1000,
        )
        modules = bp["spec"]["deployment_groups"][0]["modules"]
        comp = next(m for m in modules if m["id"] == "compute_partition")
        self.assertEqual(comp["settings"]["machine_type"], "c4-standard-192")
        self.assertEqual(comp["settings"]["boot_disk_type"], "hyperdisk-balanced")
        self.assertIn("data_disks", comp["settings"])

    def test_a3_ultra_generation(self):
        self.assertIn("a3-ultra", MACHINE_SPECS)
        spec = MACHINE_SPECS["a3-ultra"]
        self.assertEqual(spec["machine_type"], "a3-ultragpu-8g")
        self.assertEqual(spec["gpu_count"], 8)
        self.assertEqual(spec["gpu_type"], "nvidia-h200-141gb-sxm5")
        self.assertEqual(spec["boot_disk_type"], "hyperdisk-balanced")

        bp = generate_blueprint(
            project_id="test-proj",
            region="us-central1",
            zone="us-central1-a",
            cluster_name="a3-ultra-cluster",
            compute_family="a3-ultra",
            max_nodes=8,
            storage_type="filestore-high-scale",
            enable_compact_placement=True,
            enable_spot=False,
        )
        modules = bp["spec"]["deployment_groups"][0]["modules"]
        comp = next(m for m in modules if m["id"] == "compute_partition")
        self.assertEqual(comp["settings"]["machine_type"], "a3-ultragpu-8g")
        self.assertEqual(comp["settings"]["gpu"]["type"], "nvidia-h200-141gb-sxm5")
        self.assertEqual(comp["settings"]["gpu"]["count"], 8)

    def test_a4x_generation(self):
        self.assertIn("a4x", MACHINE_SPECS)
        spec = MACHINE_SPECS["a4x"]
        self.assertEqual(spec["machine_type"], "a4x-highgpu-4g")
        self.assertEqual(spec["gpu_count"], 4)
        self.assertEqual(spec["gpu_type"], "nvidia-gb200")
        self.assertEqual(spec["boot_disk_type"], "hyperdisk-balanced")

    def test_gcsfuse_storage_generation(self):
        bp = generate_blueprint(
            project_id="test-proj",
            region="us-central1",
            zone="us-central1-a",
            cluster_name="gcs-cluster",
            compute_family="h3",
            max_nodes=4,
            storage_type="gcsfuse",
            enable_compact_placement=False,
            enable_spot=False,
        )
        modules = bp["spec"]["deployment_groups"][0]["modules"]
        storage = next(m for m in modules if m["id"] == "shared_storage")
        self.assertEqual(storage["source"], "community/modules/file-system/gcsfuse")
        self.assertEqual(storage["settings"]["local_mount"], "/gcs")
        self.assertFalse(any(m["id"] == "placement_group" for m in modules))

    def test_no_compact_placement(self):
        bp = generate_blueprint(
            project_id="test-proj",
            region="us-central1",
            zone="us-central1-a",
            cluster_name="no-compact-cluster",
            compute_family="c4",
            max_nodes=8,
            storage_type="none",
            enable_compact_placement=False,
            enable_spot=False,
        )
        modules = bp["spec"]["deployment_groups"][0]["modules"]
        self.assertFalse(any(m["id"] == "placement_group" for m in modules))
        comp = next(m for m in modules if m["id"] == "compute_partition")
        self.assertFalse(comp["settings"]["enable_placement"])

    def test_batch_flexibility_policy_cae(self):
        policy = generate_batch_flexibility_policy("cae-cfd")
        selections = policy["instanceSelections"]
        self.assertEqual(selections[0]["rank"], 0)
        self.assertIn("c4-standard-192", selections[0]["machineTypes"])
        self.assertEqual(selections[1]["rank"], 1)
        self.assertIn("h3-standard-88", selections[1]["machineTypes"])
        self.assertEqual(selections[2]["rank"], 2)

    def test_batch_flexibility_policy_gpu(self):
        policy = generate_batch_flexibility_policy("md-gpu")
        selections = policy["instanceSelections"]
        self.assertEqual(selections[0]["rank"], 0)
        self.assertIn("a4-highgpu-8g", selections[0]["machineTypes"])
        self.assertIn("a4x-highgpu-4g", selections[0]["machineTypes"])
        self.assertEqual(selections[1]["rank"], 1)
        self.assertIn("a3-ultragpu-8g", selections[1]["machineTypes"])
        self.assertIn("a3-highgpu-8g", selections[1]["machineTypes"])

    def test_dedicated_login_node_module(self):
        bp = generate_blueprint(
            project_id="test-proj",
            region="us-central1",
            zone="us-central1-a",
            cluster_name="dedicated-login-cluster",
            compute_family="c4",
            max_nodes=16,
            storage_type="filestore-high-scale",
            enable_compact_placement=False,
            enable_spot=False,
            use_dedicated_login_module=True,
        )
        modules = bp["spec"]["deployment_groups"][0]["modules"]
        login_mod = next((m for m in modules if m["id"] == "slurm_login"), None)
        self.assertIsNotNone(login_mod)
        self.assertEqual(login_mod["source"], "community/modules/compute/schedmd-slurm-gcp-v6-login")
        self.assertEqual(login_mod["settings"]["machine_type"], "n4-standard-4")
        self.assertEqual(login_mod["settings"]["boot_disk_type"], "hyperdisk-balanced")

        controller = next(m for m in modules if m["id"] == "slurm_controller")
        self.assertIn("slurm_login", controller["use"])
        self.assertNotIn("login_nodes", controller["settings"])

    def test_gen4_cae_c4d_highmem_g4_and_managed_lustre_scratch(self):
        self.assertIn("c4d-highmem", MACHINE_SPECS)
        self.assertEqual(MACHINE_SPECS["c4d-highmem"]["machine_type"], "c4d-highmem-192")
        self.assertEqual(MACHINE_SPECS["c4d-highmem"]["boot_disk_type"], "hyperdisk-balanced")

        self.assertIn("g4", MACHINE_SPECS)
        self.assertEqual(MACHINE_SPECS["g4"]["machine_type"], "g4-standard-48")
        self.assertEqual(MACHINE_SPECS["g4"]["gpu_type"], "nvidia-rtx-pro-6000")
        self.assertEqual(MACHINE_SPECS["g4"]["boot_disk_type"], "hyperdisk-balanced")

        bp = generate_blueprint(
            project_id="test-proj",
            region="us-central1",
            zone="us-central1-a",
            cluster_name="cae-gen4-cluster",
            compute_family="h4d",
            max_nodes=32,
            storage_type="managed-lustre",
            enable_compact_placement=True,
            enable_spot=False,
        )
        modules = bp["spec"]["deployment_groups"][0]["modules"]
        psa = next((m for m in modules if m["id"] == "private_service_access"), None)
        self.assertIsNotNone(psa)
        self.assertEqual(psa["source"], "modules/network/private-service-access")

        lustre = next((m for m in modules if m["id"] == "shared_storage"), None)
        self.assertIsNotNone(lustre)
        self.assertEqual(lustre["source"], "modules/file-system/managed-lustre")
        self.assertEqual(lustre["settings"]["local_mount"], "/scratch")

if __name__ == "__main__":
    unittest.main()
