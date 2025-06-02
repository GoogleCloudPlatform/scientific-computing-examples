# Creates a event in the GCE api to enhance 
resource "random_id" "service_suffix" {
  byte_length = 8 # This generates a 16-character hexadecimal string (8 bytes * 2 hex chars/byte)
}
data "google_project" "current_project" {}

resource "google_tags_tag_key" "solution_key" {
  parent = "${data.google_project.current_project.id}"
  short_name   = "solution-${random_id.service_suffix.hex}"
  description  = "Tag key for solution identification. Not used." 

}