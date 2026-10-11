# Google Cloud Batch w Nextflow Infrastructure optimizer web application

The **Google Cloud Batch w Nextflow Infrastructure Optimizer** is an GUI-driven web application designed to analyze complex Nextflow bioinformatics pipelines (such as `main.nf` and its sub-directory modules) and programmatically compile optimized, cost-efficient, and GCP Batch-ready `nextflow.config` files.

We allow user to pick different cost tier per bioinformatics process. Equipped with a built-in automated **QA & Validation Agent**, the application acts as an active gatekeeper to ensure compiled configurations strictly align with Google Cloud hardware compatibilities, resource limitations, and organizational standards before code is deployed.

---


## 📌 Project Overview

This repository hosts a dual-agent workflow system designed to solve the complexity of deploying genomic pipelines at scale. It bridges the gap between Bioinformatics Research and Cloud Infrastructure Engineering.

AI Studio creates a full Web GUI for "main.nf" and "nextflow.config" ingestion.
After user select the cost tiers, it will generate the Google Batch ready Nextflow config file.

Behind the scene, there are two agents:

1. **The Infrastructure & Hardware Optimizer**: Parses bioinformatics pipelines, auto-profiles scale requirements, and helps DevOps engineers map processes to optimized hardware tiers with real-time GCP cost visibility. Web-GUI allows user to adjust the cost tier dynamically.
2. **The QA & Validation Agent (Audit Gatekeeper)**: Programmatically evaluates configuration outputs across five distinct technical vectors to guarantee deployment stability and compliance with zero-tolerance cloud hardware constraints.

---

## 💼 Business Value

| Business Challenge | Optimizer Solution | Expected Business Impact |
| :--- | :--- | :--- |
| **High cloud spend** on over-provisioned bioinformatics pipelines | Dynamic hardware mapping to custom **GCP Tiers** (Spot/On-Demand) | **Up to 60% cost reduction** via optimized VM sizing and Spot usage. |
| **Configuration errors** causing runtime failures on GCP Batch | Integrated **QA & Validation Agent** verifying NVMe, SSD, and RAM ratios | **Zero-tolerance deployment errors**; eliminates wasted compute hours. |
| **Manual pipeline profiling** and resource configuration overhead | **Autonomous manifest inspection** and side-by-side GUI dual-editor | **90% faster onboarding** from pipeline scripts to cloud-ready configurations. |
| **Quota exhaustion** mid-run for high-throughput genomic data | Dynamic `--max_forks` calculation and localized `gcloud` quota validation | **Uninterrupted workflow execution** avoiding mid-run stalls or failures. |

---

## Setup / installation

Use [Google AI Studio](aistudio.google.com).  

Paste the content of the [skill.md](skill.md) file

AI studio will take care of the rest.
It may ask you to select different design.

---

## 🚀 Key Features

| Module / Phase | Feature | Capability Description |
| :--- | :--- | :--- |
| **Phase 1** | **Side-by-Side Dual-Editor GUI** | Unified input dashboard for `main.nf`, existing configs, FASTQ manifest URLs, Git repositories, and GCP environment parameters. |
| **Phase 2** | **Autonomous Workload Profiling** | Scans data sources directly to identify sample count and sizes without prompting the user. Resolves case-sensitive AST workflow blocks. |
| **Phase 3** | **Interactive Hardware Tiering** | Dynamically maps pipeline processes to specialized VM families (**Economy**, **Economy Plus**, **Business**, **First Class**) with live pricing models. |
| **Phase 4** | **State-Gated Reactive Compiler** | Output configurations remain strictly locked and compiled only upon user confirmation. Generates standard-compliant `google-batch` profiles. |
| **Phase 5** | **Automated Deployment Validation** | Provides copy-pasteable terminal instructions for target-region quota checks and outputs dynamic execution lines. |

---

## ⚙️ Technical Architecture & Workflow Phases

### Phase 1: Onboarding & Discovery

The platform initiates a structured onboarding journey. Users are presented with a highly responsive, **five-column GUI workspace** allowing input synchronization:

* **Column 1**: Nextflow Pipeline Script (`main.nf`) supporting DSL-2 syntax highlighting.
* **Column 2**: Existing Nextflow configuration (`nextflow.config`).
* **Column 3**: Data Source Location (FASTQ / CSV Manifest URI).
* **Column 4**: Pipeline Git Repository URL.
* **Column 5**: GCP Batch Parameters (Project ID, Region, Bucket WorkDir, Network, Subnetwork, and Containers).

### Phase 2: Evaluation & Analysis

The parser engine performs deep inspection on the provided environment:

* **FASTQ Data Profiling**: Automatically opens manifests and calculates exact sample counts and files sizes to understand run scale.
* **Workflow Parsing**: Extracts all AST process blocks (e.g. `process SALMON_QUANT`) using strict case-sensitive matching.
* **Git Repository Evaluation**: Searches all sub-directories and modules to compile an exhaustive list of process definitions.

### Phase 3: Hardware Tuning & Pricing

Bioinformatic processes are mapped to distinct, GCP-supported hardware tiers:

| Hardware Tier | Recommended GCP VM Family | Target Storage Configuration | Optimization Profile |
| :--- | :--- | :--- | :--- |
| **ECONOMY** | N2-standard | Standard PD | 100% Spot instances for maximum budget-friendly processing |
| **ECONOMY PLUS** | N2-standard | Local SSD | Dedicated high I/O throughput via attached scratch disks |
| **BUSINESS** | C2 / C3 / C4 | High Performance PD | On-Demand compute optimization for execution stability |
| **FIRST CLASS** | H4D / C4 / H3 | Natively Required NVMe | Max throughput, high-memory, ultra-low latency for time-critical runs |

> ⚠️ **Disk Support Rule**: Hardware mappings must strictly respect local disk compatibility. Standard H4D instances do not support Local SSDs; whereas H4D-highmem-192-lssd natively supports Local SSD, and H3-standard requires NVMe.

### Phase 4: Functional Requirements & Config Compilation

The platform compiles a production-ready `nextflow.config` file updating the pre-existing structure without destroying default parameters.

* **Profile Block**: Generated under a single `profile { google-batch { ... } }` declaration.
* **Process Alignment**: Inserts process blocks mapped using case-sensitive tags (`withName: 'SALMON_QUANT'`).
* **Workflow State Gating**: Output code blocks remain completely hidden/locked until the "Compile Config File" trigger is pressed.
* **Reactive Updates**: Once unlocked, any tier adjustment dynamically re-renders the configuration in real-time.

### Phase 5: Operational Commands & Quotas

To ensure successful deployment, the system generates:

* **Gcloud Quota Check Command**: Formulated to target the user's specific region to verify vCPUs, GPUs, and Local SSD allocations.
* **Dynamic Execution Line**: Constructs the deployment instruction with a calculated parallelization buffer:
  `nextflow run [pipeline_filename] -profile google-batch --max_forks <calculated_value>`

---

## 🧬 Bioinfo Process Hardware Selection Reference

Our reference matrix enforces correct machine pairing based on biological algorithm demands:

| Bioinformatics Process | Target Hardware Tier | Recommended Specs (vCPUs/RAM) | Key Storage / Compute Constraint |
| :--- | :--- | :--- | :--- |
| **FastQC (QC)** | Economy / Economy Plus | 4-8 vCPUs, Low RAM | Prioritize high-throughput storage I/O |
| **BWA (DNA Alignment)** | Business | 16-64 vCPUs (2:4 Ratio) | Keep standard 2 vCPUs per 4GB RAM ratio |
| **STAR (RNA Alignment)** | First Class / Memory-Optimized | Minimum 40GB RAM | Strict memory-optimized VM constraint |
| **GATK (Variant Calling)** | Business (Compute-Optimized) | High-compute, Low RAM | Use Local NVMe scratch; parallelize with single-core |
| **Kraken2 (Metagenomics)** | Ultra-High Memory | 100GB to 1TB RAM | Scaling strictly depends on database size |
| **Salmon (QUANT)** | Business / First Class | 8-16 vCPUs, 32-64GB RAM | Tight process-specific matching required |
| **MultiQC (MULTIQC)** | Economy | 2-4 vCPUs, 16-32GB RAM | Low-priority final summarization process |
| **Index (INDEX)** | Business | 8-16 vCPUs, 32-64GB RAM | High-efficiency index creation profile |

---

## 🛡️ QA & Validation Agent (Audit Framework)

The integrated Validation Agent functions as an automated peer-reviewer checking the compiled output:

| Audit Vector | Critical Checks Performed | Error Trigger Policy |
| :--- | :--- | :--- |
| **1. Parsing Integrity** | Case-sensitive name-matching for processes; autonomous sample counting | Rejects if processes are renamed (e.g., `withName: salmon_quant` instead of `SALMON_QUANT`) |
| **2. Hardware Mapping** | CPU-to-RAM ratio compliance (2 vCPUs:4GB RAM) and disk support matrix | Rejects H3 mapped to Standard Disks (requires NVMe) or H4D-standard-192 with Local SSDs |
| **3. Profile Architecture** | Checks for single `google-batch` block and exact parameter contracts | Rejects if mandatory properties like `workDir` are missing or if network paths are malformed |
| **4. State Gating** | Enforces locked config until compiler trigger; runs bracket & quotation syntax scan | Rejects syntax anomalies like unbalanced `{}` or unclosed quotes (`'` or `"`) |
| **5. Operations** | Region-specific quota validation and dynamic `--max_forks` scalability | Rejects if the run command does not scale concurrency based on actual sample size |

### Audit Response Protocol

The QA Agent issues structured reports for each compile attempt:

1. **Audit Executive Summary**: A clear declaration of the status: `[PASSED]` or `[REJECTED - ACTION REQUIRED]`.
2. **Exception & Violations Log**: Highly detailed breakdown of any rule infractions.
3. **Corrective Guidance**: Actionable remediation snippets to immediately align the configuration with engineering reference specifications.
