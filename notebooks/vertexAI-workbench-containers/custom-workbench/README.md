# Create a custom workbench image


## Overview of steps

- create a project
- enable services
- create an image repository
- build a custom image and push it to the repository
- spin up workbench images from that custom image


## Notes

- This should work well from a cloudshell.  Your `gcloud` is already auth'd and
  `docker` is installed. The only concern is the size of the base workbench
  container images... they're _huge_.
- We'll first provide example `gcloud` commands that you can customize.  We can
  put together some example code hitting the APIs directly if that's more
  useful.
