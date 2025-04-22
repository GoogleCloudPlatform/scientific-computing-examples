# A use-case for terraform_data is as a do-nothing container
# for arbitrary actions taken by a provisioner.
resource "terraform_data" "null" {
  provisioner "local-exec" {
    command = ":"
  }
}