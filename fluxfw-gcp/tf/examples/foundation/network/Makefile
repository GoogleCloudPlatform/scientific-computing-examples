DEFAULT_CONFIG=default/main.tf default/variables.tf default/outputs.tf
ZONAL_CONFIG=zonal/main.tf zonal/variables.tf zonal/outputs.tf
TERRAFORM_STATE=terraform.tfstate terraform.tfstate.backup
TERRAFORM_FILES=default/.terraform default/.terraform.lock.hcl zonal/.terraform zonal/.terraform.lock.hcl

.PHONY: init
init: 
	terraform -chdir=default init
	terraform -chdir=zonal init

.default: $(DEFAULT_CONFIG) $(DEFAULT_TFVARS)
	@[ -e .zonal ] && terraform -chdir=zonal destroy -state=$$PWD/terraform.tfstate -var project_id=$(project_id) -var region=$(region) -var network_name=$(network_name) -auto-approve && rm .zonal; true
	terraform -chdir=default apply -state=$$PWD/terraform.tfstate -var project_id=$(project_id) -var region=$(region) -auto-approve
	@touch .default

.zonal: $(ZONAL_CONFIG) $(ZONAL_TFVARS)
	@[ -e .default ] && terraform -chdir=default destroy -state=$$PWD/terraform.tfstate -var project_id=$(project_id) -var region=$(region) -auto-approve && rm .default; true
	terraform -chdir=zonal apply -state=$$PWD/terraform.tfstate -var project_id=$(project_id) -var region=$(region) -var network_name=$(network_name) -auto-approve
	@touch .zonal

.PHONY: clean
clean: 
	@[ -e .zonal ] && terraform -chdir=zonal destroy -state=$$PWD/terraform.tfstate -var project_id=$(project_id) -var region=$(region) -var network_name=$(network_name) -auto-approve && rm .zonal; true
	@[ -e .default ] && terraform -chdir=default destroy -state=$$PWD/terraform.tfstate -var project_id=$(project_id) -var region=$(region) -auto-approve && rm .default; true
	rm -f $(TERRAFORM_STATE)

.PHONY: clobber
clobber: clean
	rm -rf $(TERRAFORM_FILES)
