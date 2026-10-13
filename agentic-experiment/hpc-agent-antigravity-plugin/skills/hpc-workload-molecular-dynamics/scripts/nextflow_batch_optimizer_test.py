import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nextflow_batch_optimizer import NextflowBatchOptimizer

class TestNextflowBatchOptimizer(unittest.TestCase):
    def setUp(self):
        self.optimizer = NextflowBatchOptimizer()

    def test_parse_main_nf_case_sensitive(self):
        main_nf_sample = """
        nextflow.enable.dsl=2

        process FASTQC {
            tag "$sample_id"
            input: tuple val(sample_id), path(reads)
            output: path("*.html")
            script: "fastqc $reads"
        }

        process SALMON_QUANT {
            tag "$sample_id"
            input: tuple val(sample_id), path(reads), path(index)
            output: path("${sample_id}_quant")
            script: "salmon quant -i $index -r $reads -o ${sample_id}_quant"
        }

        process MultiQC {
            input: path('*')
            output: path("multiqc_report.html")
            script: "multiqc ."
        }
        """
        procs = self.optimizer.parse_main_nf(main_nf_sample)
        self.assertEqual(procs, ["FASTQC", "SALMON_QUANT", "MultiQC"])
        # Verify exact case preservation
        self.assertIn("SALMON_QUANT", procs)
        self.assertNotIn("salmon_quant", procs)

    def test_biological_process_hardware_tiering(self):
        star_profile = self.optimizer.classify_process("STAR_ALIGN")
        self.assertGreaterEqual(star_profile["min_memory_gb"], 40)

        kraken_profile = self.optimizer.classify_process("KRAKEN2_CLASSIFY")
        self.assertGreaterEqual(kraken_profile["min_memory_gb"], 100)

        bwa_profile = self.optimizer.classify_process("BWA_MEM")
        # Check 4GB RAM per 2 vCPUs baseline (2 GB/vCPU)
        self.assertEqual(bwa_profile["memory_gb"] / bwa_profile["vcpus"], 2.0)

    def test_calculate_max_forks(self):
        # 100 samples, avg 20 vCPUs, 1000 quota -> max parallel = 800 / 20 = 40
        forks = self.optimizer.calculate_max_forks(sample_count=100, process_vcpus=[16, 24])
        self.assertEqual(forks, 40)

        # 5 samples -> limited by sample count
        forks_small = self.optimizer.calculate_max_forks(sample_count=5, process_vcpus=[16, 24])
        self.assertEqual(forks_small, 5)

        # Zero or empty vcpus list should not divide by zero
        forks_zero = self.optimizer.calculate_max_forks(sample_count=10, process_vcpus=[0])
        self.assertGreaterEqual(forks_zero, 1)

    def test_machine_type_selection_valid_shapes_and_capacity(self):
        # 1. 32 vCPUs on C3 (business) must choose c3-standard-44, NOT underprovisioned c3-standard-8
        c3_shape = self.optimizer.select_machine_type("business", vcpus=32, memory_gb=64, proc_name="BWA_MEM")
        self.assertEqual(c3_shape, "c3-standard-44")

        # 2. 12 vCPUs on N2 (economy) must choose valid n2-standard-16, NOT invalid n2-standard-12
        n2_shape = self.optimizer.select_machine_type("economy", vcpus=12, memory_gb=48, proc_name="SALMON_QUANT")
        self.assertEqual(n2_shape, "n2-standard-16")

        # 3. STAR alignment must satisfy memory floor >= 40GB
        star_shape = self.optimizer.select_machine_type("business", vcpus=16, memory_gb=64, proc_name="STAR_ALIGN")
        self.assertEqual(star_shape, "c3-standard-22")

        # 4. Kraken2 metagenomics must satisfy memory floor >= 100GB
        kraken_shape = self.optimizer.select_machine_type("business", vcpus=32, memory_gb=128, proc_name="KRAKEN2")
        self.assertEqual(kraken_shape, "n2-highmem-32")

    def test_generate_and_audit_clean_profile(self):
        procs = ["FASTQC", "BWA_MEM", "STAR_ALIGN", "SALMON_QUANT", "MULTIQC"]
        profile_str = self.optimizer.generate_nextflow_config_profile(
            processes=procs,
            project_id="my-bio-project",
            region="us-central1",
            workdir_gcs="gs://bio-bucket/work",
            network="my-vpc",
            subnetwork="my-subnet",
            tier="business",
            spot=False,
            reads_param="gs://bio-bucket/data/*.fastq.gz",
            transcriptome_param="gs://bio-bucket/ref.fa",
            multiqc_param="gs://bio-bucket/qc",
        )

        self.assertIn("withName: 'FASTQC'", profile_str)
        self.assertIn("withName: 'STAR_ALIGN'", profile_str)
        self.assertIn("withName: 'SALMON_QUANT'", profile_str)
        # Verify BWA_MEM gets sufficient vCPUs
        self.assertIn("machineType = 'c3-standard-44'", profile_str)
        self.assertIn("process.executor = 'google-batch'", profile_str)
        self.assertIn("workDir = 'gs://bio-bucket/work'", profile_str)
        self.assertIn("global/networks/my-vpc", profile_str)
        self.assertIn("params.reads = 'gs://bio-bucket/data/*.fastq.gz'", profile_str)

        # Audit should pass cleanly
        audit_res = self.optimizer.audit_config(
            config_content=profile_str,
            main_nf_processes=procs,
            target_region="us-central1",
        )
        self.assertTrue(audit_res["passed"])
        self.assertEqual(audit_res["status"], "[PASSED]")
        self.assertEqual(len(audit_res["violations"]), 0)

    def test_audit_detects_casing_mismatch(self):
        config_text = """
        profiles {
          'google-batch' {
            params.reads = ''
            params.transcriptome = ''
            params.multiqc = ''
            workDir = 'gs://bucket/work'
            google.location = 'us-central1'
            google.project = 'test-proj'
            process.executor = 'google-batch'
            process {
              withName: 'salmon_quant' { cpus = 8; memory = '32.GB'; }
            }
          }
        }
        """
        # main.nf had uppercase SALMON_QUANT
        audit_res = self.optimizer.audit_config(
            config_content=config_text,
            main_nf_processes=["SALMON_QUANT"],
        )
        self.assertFalse(audit_res["passed"])
        self.assertTrue(any("Exact Naming" in v for v in audit_res["violations"]))

    def test_audit_zero_tolerance_h4d_local_ssd_violation(self):
        config_text = """
        profiles {
          'google-batch' {
            params.reads = ''
            params.transcriptome = ''
            params.multiqc = ''
            workDir = 'gs://bucket/work'
            google.location = 'us-central1'
            google.project = 'test-proj'
            process.executor = 'google-batch'
            process {
              withName: 'FASTQC' {
                machineType = 'h4d-standard-192'
                disk = 'local-ssd'
              }
            }
          }
        }
        """
        audit_res = self.optimizer.audit_config(
            config_content=config_text,
            main_nf_processes=["FASTQC"],
        )
        self.assertFalse(audit_res["passed"])
        self.assertTrue(any("H4D-standard-192 does not support Local SSDs" in v for v in audit_res["violations"]))

    def test_audit_zero_tolerance_h3_non_nvme_violation(self):
        config_text = """
        profiles {
          'google-batch' {
            params.reads = ''
            params.transcriptome = ''
            params.multiqc = ''
            workDir = 'gs://bucket/work'
            google.location = 'us-central1'
            google.project = 'test-proj'
            process.executor = 'google-batch'
            process {
              withName: 'FASTQC' {
                machineType = 'h3-standard-88'
                disk = 'local-ssd'
              }
            }
          }
        }
        """
        audit_res = self.optimizer.audit_config(
            config_content=config_text,
            main_nf_processes=["FASTQC"],
        )
        self.assertFalse(audit_res["passed"])
        self.assertTrue(any("H3 instance family supports NVMe storage only" in v for v in audit_res["violations"]))

    def test_audit_syntax_unbalanced_braces(self):
        config_text = """
        profiles {
          'google-batch' {
            params.reads = ''
            params.transcriptome = ''
            params.multiqc = ''
            workDir = 'gs://bucket/work'
            google.location = 'us-central1'
            google.project = 'test-proj'
            process.executor = 'google-batch'
        """
        audit_res = self.optimizer.audit_config(config_content=config_text)
        self.assertFalse(audit_res["passed"])
        self.assertTrue(any("Unbalanced curly braces" in v for v in audit_res["violations"]))

if __name__ == "__main__":
    unittest.main()
