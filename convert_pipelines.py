import argparse
import copy
import json
import os
import sys
import pprint

import requests
import yaml
import yaml.dumper

from collections import OrderedDict


class UnsortableList(list):
  def sort(self, *args, **kwargs):
    pass


class UnsortableOrderedDict(OrderedDict):
  """
  Because PyYAML sorts things. Guh.
  """
  def items(self, *args, **kwargs):
    return UnsortableList(OrderedDict.items(self, *args, **kwargs))


def convert(pipeline_config):
  template = UnsortableOrderedDict([
    ('schema', '1'),
    ('id', 'generatedTemplate'),
    ('metadata', UnsortableOrderedDict([
      ('name', pipeline_config['name'] if 'name' in pipeline_config else 'GIVE ME A NAME'),
      ('description', pipeline_config['description'] if 'description' in pipeline_config else 'GIVE ME A DESCRIPTION'),
      ('owner', pipeline_config['lastModifiedBy']),
      ('scopes', [])
    ])),
    ('protect', False),
    ('configuration', UnsortableOrderedDict([
      ('concurrentExecutions', UnsortableOrderedDict([
        ('parallel', pipeline_config['parallel']),
        ('limitConcurrent', pipeline_config['limitConcurrent'])
      ])),
      ('triggers', _convert_triggers(pipeline_config['triggers']) if 'triggers' in pipeline_config else []),
      ('parameters', pipeline_config['parameterConfig'] if 'parameterConfig' in pipeline_config else []),
      ('notifications', _convert_notifications(pipeline_config['notifications']) if 'notifications' in pipeline_config else [])
    ])),
    ('variables', []),
    ('stages', _convert_stages(pipeline_config['stages']))
  ])
  return template


def _convert_stages(stages):
  ret = []
  for s in stages:
    depends_on = []
    if 'requisiteStageRefIds' in s and len(s['requisiteStageRefIds']) > 0:
      depends_on = [_get_ref_stage_id(stages, ref_id) for ref_id in s['requisiteStageRefIds']]

    stage = UnsortableOrderedDict([
      ('id', _get_stage_id(s['type'], s['refId'])),
      ('type', s['type']),
      ('dependsOn', depends_on),
      ('name', s['name']),
      ('config', _scrub_stage_config(s))
    ])

    ret.append(stage)

  return ret


def _get_ref_stage_id(stages, ref_id):
  stage = [s for s in stages if s['refId'] == ref_id][0]
  return _get_stage_id(stage['type'], stage['refId'])


def _get_stage_id(stage_type, stage_ref_id):
  return ''.join([stage_type, stage_ref_id])


def _scrub_stage_config(stage):
  s = copy.deepcopy(stage)
  del s['type']
  del s['name']
  del s['refId']
  del s['requisiteStageRefIds']
  return s


def _convert_triggers(triggers):
  ret = []
  i = 0
  for t in triggers:
    i += 1
    t['name'] = 'unnamed' + str(i)
    ret.append(t)
  return ret


def _convert_notifications(notifications):
  i = 0
  ret = []
  for n in notifications:
    i += 1
    n['name'] = '{}{}'.format(n['type'], i)
    ret.append(n)
  return ret


def render(pipeline_template):
  yaml.add_representer(UnsortableOrderedDict, yaml.representer.SafeRepresenter.represent_dict, Dumper=yaml.dumper.SafeDumper)
  return '''\
# GENERATED BY spin-dcd-converter
#
# The output generated by this tool should be used as a base for further
# modifications. It does not make assumptions as to what things can be made into
# variables, modules or Jinja templates. This is your responsibility as the
# owner of the template.
#
# Some recommendations to massage the initial output:
#
# * Give your pipeline template a unique ID. Typically it's best to namespace the
#   template ID, e.g. "myteam-mytemplate".
# * Rename the pipeline stage IDs, notification names and trigger names to be 
#   more meaningful. Enumerated stage IDs is ultimately a detriment for 
#   long-term maintainability.
# * Best intentions are made to order most things, but the list of stages 
#   themselves are not ordered: Rearrange the stages so that they're roughly 
#   chronological.
{template}
'''.format(template=yaml.safe_dump(pipeline_template, default_flow_style=False))

def get_pipeline_config(api_host, app, pipeline_config_id):
  # TODO rz - I'm not proud of this, but I want to move on
  session_cookie = os.getenv('API_SESSION')
  cookies = {} if session_cookie is None else {'SESSION': session_cookie}
  endpoint = '{host}/applications/{app}/pipelineConfigs/{config_id}'.format(
    host=api_host, 
    app=app,
    config_id=pipeline_config_id
  )

  if DEBUG_MODE:
    print('Endpoint:\n\t' + endpoint)
    print('Cookie:\n\t' + str(cookies))

  r = requests.get(endpoint, cookies=cookies)

  if r.status_code != 200:
    print('failed getting pipeline config: ' + str(r.status_code))
    return False
  
  return r.json()


def parser():
  p = argparse.ArgumentParser()
  p.add_argument('app')
  p.add_argument('pipelineConfigId')
  p.add_argument('--debug', dest='debug', help='Enable debug mode',
    default=False, type=lambda x: (str(x).lower() in ['true','1', 'yes']))
  return p

DEBUG_MODE=False

if __name__ == '__main__':
  api_host = os.getenv('API_HOST')
  args = parser().parse_args()
  DEBUG_MODE = args.debug
  if api_host is None:
    print('API_HOST must be set to your Spinnaker API')
    sys.exit(1)
  if api_host[-1:] == '/':
    api_host = api_host[:-1]

  pipeline_config = get_pipeline_config(api_host, args.app, args.pipelineConfigId)
  if DEBUG_MODE:
    print('Response:\n---\n{json}\n---'.format(json=pipeline_config))
  template = convert(pipeline_config)
  print(render(template))
