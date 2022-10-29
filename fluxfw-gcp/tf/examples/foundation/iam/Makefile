DEFAULT_CONFIG=default/main.tf default/outputs.tf default/state.tf
TERRAFORM_STATE=terraform.tfstate terraform.tfstate.backup
TERRAFORM_FILES=default/.terraform default/.terraform.lock.hcl

.PHONY: init
init: 
	terraform -chdir=default init

.default: $(DEFAULT_CONFIG)
	terraform -chdir=default apply -state=$$PWD/terraform.tfstate -auto-approve
	@touch .default

.PHONY: clean
clean: 
	@[ -e .default ] && terraform -chdir=default destroy -state=$$PWD/terraform.tfstate -auto-approve && rm .default; true
	rm -f $(TERRAFORM_STATE)

.PHONY: clobber
clobber: clean
	rm -rf $(TERRAFORM_FILES)
