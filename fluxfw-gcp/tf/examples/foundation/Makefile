NETWORK_STATE = network/terraform.tfstate
IAM_STATE     = iam/terraform.tfstate
STORAGE_STATE = storage/terraform.tfstate

project_id = $$(gcloud config get-value core/project)
region     = $$(gcloud config get-value compute/region)

network_type = default
network_name = foundation-net-01
storage_name = foundation-storage-01
share_name   = home

all: network iam storage

.PHONY: network
network: $(NETWORK_STATE)

$(NETWORK_STATE):
	@cd network && $(MAKE) .$(network_type) project_id=$(project_id) region=$(region) network_name=$(network_name)

.PHONY: iam
iam: $(IAM_STATE)

$(IAM_STATE): $(NETWORK_STATE)
	@cd iam && $(MAKE) .default

.PHONY: storage
storage: $(STORAGE_STATE)

$(STORAGE_STATE): $(NETWORK_STATE)
	@cd storage && $(MAKE) .filestore storage_name=$(storage_name) share_name=$(share_name)

.PHONY: clean
clean:
	cd storage && $(MAKE) clean storage_name=$(storage_name) share_name=$(share_name)
	cd iam && $(MAKE) clean
	cd network && $(MAKE) clean project_id=$(project_id) region=$(region) network_name=$(network_name)
