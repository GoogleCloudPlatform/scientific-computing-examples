FILESTORE_CONFIG=filestore/main.tf filestore/variables.tf filestore/outputs.tf
TERRAFORM_STATE=terraform.tfstate terraform.tfstate.backup
TERRAFORM_FILES=filestore/.terraform filestore/.terraform.lock.hcl

.PHONY: init
init: 
	terraform -chdir=filestore init

.filestore: $(FILESTORE_CONFIG) $(FILESTORE_TFVARS)
	terraform -chdir=filestore apply -state=$$PWD/terraform.tfstate -var name=$(storage_name) -var share_name=$(share_name) -auto-approve
	@touch .filestore

.PHONY: clean
clean: 
	@[ -e .filestore ] && terraform -chdir=filestore destroy -state=$$PWD/terraform.tfstate -var name=$(storage_name) -var share_name=$(share_name) -auto-approve && rm .filestore; true
	rm -f $(TERRAFORM_STATE)

.PHONY: clobber
clobber: clean
	rm -rf $(TERRAFORM_FILES)
