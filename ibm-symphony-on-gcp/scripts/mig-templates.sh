python3   -c "
import json
import sys


# The structure of the template to be reflected in JSON
def make_template(id,max,mtype,ncpus,nram,zone,mig):

    temp =  {
            'templateId': id,
            'maxNumber': max,
            'attributes': {
                'type': ['String', mtype],
                'ncpus': ['Numeric', ncpus],
                'nram': ['Numeric', nram]
            },
            'gcp_zone': zone,
            'gcp_instance_group': mig
        }
    return(temp)

# Required info is passed semicolon delimited for each template
template_args = sys.argv[1].split(';')

# Start the JSON structure
template_output = {
   'templates': []
}

# Loop over templates
for arg in template_args:
  
  #parse the settings for each template
  (id,max,mtype,ncpus,nram,zone,mig) = arg.split(',')

  # Append the template to the stub
  template_output['templates'].append(make_template(id,max,mtype,ncpus,nram,zone,mig))

print(json.dumps(template_output,indent=2))
" \
"$@" \
> conf/providers/gcpgceinst/gcpgceinstprov_templates.json