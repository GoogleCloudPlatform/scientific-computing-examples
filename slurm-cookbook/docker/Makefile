.PHONY: plan apply destroy

$SCRIPTS/custom-compute-install: custom-compute-install
	ln -sfn $$PWD/custom-compute-install ../../../scripts/custom-compute-install

$SCRIPTS/custom-controller-install: custom-controller-install
	ln -sfn $$PWD/custom-controller-install ../../../scripts/custom-controller-install

plan:
	terraform plan -var-file=basic.tfvars -out terraform.tfplan

apply:  $SCRIPTS/custom-controller-install $SCRIPTS/custom-compute-install
	terraform apply -var-file=basic.tfvars -auto-approve

destroy:
	terraform destroy -var-file=basic.tfvars -auto-approve

apply_h:  $SCRIPTS/custom-controller-install $SCRIPTS/custom-compute-install
	terraform apply -var-file=hiroshi.tfvars -auto-approve

destroy_h:
	terraform destroy -var-file=hiroshi.tfvars -auto-approve
