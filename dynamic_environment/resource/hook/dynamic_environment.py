import logging
import json
import os
import platform
import re
import ftrack
import ftrack_api

logging.basicConfig()
logger = logging.getLogger()


def load_env(path):
    """Load options json from path"""

    with open(path, "r") as f:
        return json.load(f)


def appendPath(path, key, environment):
    '''Append *path* to *key* in *environment*.'''
    try:
        environment[key] = (
            os.pathsep.join([
                environment[key], str(path)
            ])
        )
    except KeyError:
        environment[key] = str(path)

    return environment


def dynamic_environment(event):
    '''Modify the application environment.'''
    data = event['data']
    print "\n>>> data: {}".format(data)
    app = data['application']
    print "\n>>> app: {}".format(app)
    logger.info('APP INFO:{}'.format(app))

    taskid = data['context']['selection'][0].get('entityId')
    print "\n>>> taskid: {}".format(taskid)
    session = ftrack_api.Session()
    print "\n>>> session: {}".format(session)
    task = session.query('Task where id is {0}'.format(taskid)).one()
    print "\n>>> task: {}".format(task)
    # get location of json environmnets from env var
    try:
        env_paths = os.environ['FTRACK_APP_ENVIRONMENTS'].split(os.pathsep)
    except KeyError:
        raise Exception('"FTRACK_APP_ENVIRONMENTS" environment variable not\
                         found. please create it and point it to a folder with\
                         your .json config files.')
    env_files = []

    for env_path in env_paths:

        print "\n>>> env_path: {}".format(env_path)

        # determine config file for version independent environment
        print "\n>>> app['identifier']: {}".format(app['identifier'])
        if not app['identifier'].startswith('nuke_studio'):
            app_name, app_variant = app['identifier'].split('_')
        else:
            _app, name, app_variant = app['identifier'].split('_')
            app_name = '_'.join([_app, name])
        app_file_name = '{}.json'.format(app_name)
        env_files.append(os.path.join(env_path, app_file_name))

        # determine config file for version dependent environment
        variant_file_name = '{}.json'.format(app['identifier'])
        env_files.append(os.path.join(env_path, variant_file_name))
        print "\n>>> env_files: {}".format(env_files)

        # collect all parents from the task
        parents = []
        for item in task['link']:
            parents.append(session.get(item['type'], item['id']))
        print "\n>>> parents: {}".format(parents)
        # collect all the 'environment' attributes from parents
        enviro_attr = None
        for parent in parents:
            # check if the attribute is empty, if not use it
            if parent['custom_attributes']['environment']:
                print "\n>>> parent: {}".format(parent)
                enviro_attr = parent['custom_attributes']['environment']
                print "\n>>> enviro_attr: {}".format(enviro_attr)

        if not enviro_attr and not env_files:
            logger.info('No additional environmnet found.')
            return

        logger.debug('ENVIRO Attr:{}'.format(enviro_attr))

        if enviro_attr:
            # separate list of tools from environmnet attr to individual tools
            environments_to_add = enviro_attr.split(',')

            # construct the path to corresponding json file by adding
            # tool, app version and json extension
            for tool in environments_to_add:
                tool = tool.strip()
                env_files.append(os.path.join(tool, '{}.json'.format(app_name)))
                tool_version = os.path.join(tool, '_'.join([app_name, app_variant]))
                tool_env_file = '{}.json'.format(tool_version)
                print "\n>>> tool_env_file: {}".format(tool_env_file)
                env_files.append(os.path.join(env_path, tool_env_file))
            print "\n>>> env_files: {}".format(env_files)

    env_add = []

    # loop through config files
    for env_file in env_files:
        try:
            logger.info('Adding {} to the environment'.format(env_file))
            env_add = load_env(env_file)
            print "\n>>> env_add: {}".format(env_add)
        except:
            logger.info('Unable to find the environment file.')
            logger.info('Make sure that {} exists.'.format(env_file))
            env_add = None

        # Add each path in config file to the environment
        if env_add:
            for variable in env_add:
                for path in env_add[variable]:
                    print "\n>>> env_add[variable].path: {}".format(path)
                    keys = re.findall(r'{.*?}', path)
                    for key in keys:
                        found_key = os.path.abspath(os.environ.get(key[1:-1]))
                        path = path.replace(key, found_key)
                    appendPath(path, str(variable), data['options']['env'])


def register(registry, **kw):
    '''Register location plugin.'''

    # Validate that registry is the correct ftrack.Registry. If not,
    # assume that register is being called with another purpose or from a
    # new or incompatible API and return without doing anything.
    if registry is not ftrack.EVENT_HANDLERS:
        # Exit to avoid registering this plugin again.
        return

    ftrack.EVENT_HUB.subscribe(
        'topic=ftrack.connect.application.launch',
        dynamic_environment
    )


if __name__ == '__main__':
    logger.setLevel(logging.DEBUG)

    ftrack.setup()

    ftrack.EVENT_HUB.subscribe(
        'topic=ftrack.connect.application.launch',
        dynamic_environment)
    ftrack.EVENT_HUB.wait()
