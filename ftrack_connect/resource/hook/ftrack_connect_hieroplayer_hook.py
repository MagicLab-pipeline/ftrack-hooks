# :coding: utf-8
# :copyright: Copyright (c) 2015 ftrack

import getpass
import logging
import sys
import pprint
import os
import json
import re

import ftrack
import ftrack_connect.application
import ftrack_connect_hieroplayer


ACTION_IDENTIFIER = 'ftrack-connect-launch-hieroplayer_with_review'

FTRACK_CONNECT_HIEROPLAYER_PATH = os.environ.get(
    'FTRACK_CONNECT_HIEROPLAYER_PATH',
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), '..', 'hieroplayer'
        )
    )
)


class DiscoverApplicationsHook(object):
    '''Default action.discover hook.'''

    identifier = ACTION_IDENTIFIER

    def __init__(self, applicationStore):
        '''Instantiate hook with *applicationStore*.

        *applicationStore* should be an instance of
        :class:`ftrack_connect.application.ApplicationStore`

        '''
        super(DiscoverApplicationsHook, self).__init__()
        self.logger = logging.getLogger(
            __name__ + '.' + self.__class__.__name__
        )
        self.applicationStore = applicationStore

    def __call__(self, event):
        '''Handle *event*.'''

        items = []
        applications = self.applicationStore.applications
        applications = sorted(
            applications, key=lambda application: application['label']
        )

        for application in applications:
            applicationIdentifier = application['identifier']
            label = application['label']
            items.append({
                'actionIdentifier': self.identifier,
                'label': label,
                'variant': application.get('variant', None),
                'description': application.get('description', None),
                'icon': application.get('icon', 'default'),
                'applicationIdentifier': applicationIdentifier
            })

        return {
            'items': items
        }


class LaunchApplicationHook(object):

    def __init__(self, launcher):
        '''Initialise hook with *launcher*.

        *launcher* should be an instance of
        :class:`ftrack_connect.application.ApplicationLauncher`.

        '''
        super(LaunchApplicationHook, self).__init__()
        self.logger = logging.getLogger(
            'ftrack.hook.' + self.__class__.__name__
        )
        self.launcher = launcher

    def __call__(self, event):
        '''Handle *event*.

        event['data'] should contain:

            *applicationIdentifier* to identify which application to start.
            *selection* to load in review timeline.
        '''
        # Prevent further processing by other listeners.
        # TODO: Only do this when actually have managed to launch a relevant
        # application.
        event.stop()

        applicationIdentifier = (
            event['data']['applicationIdentifier']
        )

        # If started from custom 'Launch HieroPlayer' menu in ftrack
        # the applicationIdentifier is missing version. Rewrite
        # to match any hieroplayer version.
        if applicationIdentifier == 'hieroplayer_with_review':
            applicationIdentifier = 'hieroplayer*'

        context = event['data'].copy()

        # Rewrite original selection to a playlist.
        context['selection'] = self._createPlaylistFromSelection(
            context['selection']
        )

        return self.launcher.launch(
            applicationIdentifier, context
        )

    def _createPlaylistFromSelection(self, selection):
        '''Return new selection with temporary playlist from *selection*.'''

        # If selection is only one entity we don't need to create
        # a playlist.
        if len(selection) == 1:
            return selection

        playlist = []
        for entity in selection:
            playlist.append({
                'id': entity['entityId'],
                'type': entity['entityType']
            })

        playlist = ftrack.createTempData(json.dumps(playlist))

        selection = [{
            'entityType': 'tempdata',
            'entityId': playlist.getId()
        }]

        return selection


class ApplicationLauncher(ftrack_connect.application.ApplicationLauncher):
    '''Launch HieroPlayer.'''

    def _getApplicationEnvironment(self, application, context):
        '''Modify and return environment with legacy plugins added.'''
        environment = super(
            ApplicationLauncher, self
        )._getApplicationEnvironment(
            application, context
        )

        environment['HIERO_PLUGIN_PATH'] = os.path.join(
            FTRACK_CONNECT_HIEROPLAYER_PATH
        )

        return environment


class ApplicationStore(ftrack_connect.application.ApplicationStore):

    def _discoverApplications(self):
        '''Return a list of applications that can be launched from this host.

        An application should be of the form:

            dict(
                'identifier': 'name_version',
                'label': 'Name',
                'variant': 'version',
                'description': 'description',
                'path': 'Absolute path to the file',
                'version': 'Version of the application',
                'icon': 'URL or name of predefined icon'
            )

        '''
        applications = []

        if sys.platform == 'darwin':
            prefix = ['/', 'Applications']

            applications.extend(self._searchFilesystem(
                expression=prefix + ['HieroPlayer.*', 'HieroPlayer\d[\w.]+.app'],
                label='Review with HieroPlayer',
                variant='{version}',
                applicationIdentifier='hieroplayer_{version}_with_review',
                icon='hieroplayer'
            ))

            applications.extend(self._searchFilesystem(
                expression=prefix + ['Nuke.*', 'HieroPlayer\d[\w.]+.app'],
                label='Review with HieroPlayer',
                variant='{version}',
                applicationIdentifier='hieroplayer_{version}_with_review',
                icon='hieroplayer'
            ))

        elif sys.platform == 'win32':
            prefix = ['C:\\', 'Program Files.*']

            applications.extend(self._searchFilesystem(
                expression=prefix + [
                    'HieroPlayer\d.+', 'hieroplayer.exe'
                ],
                label='Review with HieroPlayer',
                variant='{version}',
                applicationIdentifier='hieroplayer_{version}_with_review',
                icon='hieroplayer'
            ))

            # Somewhere along the way The Foundry changed the default install
            # directory. Add the old directory as expression to find old
            # installations of HieroPlayer as well.
            #
            # TODO: Refactor this once ``_searchFilesystem`` is more
            # sophisticated.
            applications.extend(self._searchFilesystem(
                expression=prefix + [
                    'The Foundry', 'HieroPlayer\d.+', 'hieroplayer.exe'
                ],
                label='Review with HieroPlayer',
                variant='{version}',
                applicationIdentifier='hieroplayer_{version}_with_review',
                icon='hieroplayer'
            ))

            version_expression = re.compile(
                r'Nuke(?P<version>[\d.]+[\w\d.]*)'
            )

            applications.extend(self._searchFilesystem(
                expression=prefix + ['Nuke.*', 'Nuke\d.+.exe'],
                versionExpression=version_expression,
                label='Review with HieroPlayer',
                variant='{version}',
                applicationIdentifier='hieroplayer_{version}_with_review',
                icon='hieroplayer',
                launchArguments=['--player']
            ))

        elif sys.platform == 'linux2':

            applications.extend(self._searchFilesystem(
                versionExpression=r'HieroPlayer(?P<version>.*)\/.+$',
                expression=[
                    '/', 'usr', 'local', 'HieroPlayer.*',
                    'bin', 'HieroPlayer\d.+'
                ],
                label='Review with HieroPlayer',
                variant='{version}',
                applicationIdentifier='hieroplayer_{version}_with_review',
                icon='hieroplayer'
            ))

            applications.extend(self._searchFilesystem(
                expression=['/', 'usr', 'local', 'Nuke.*', 'Nuke\d.+'],
                label='Review with HieroPlayer',
                variant='{version}',
                applicationIdentifier='hieroplayer_{version}_with_review',
                icon='hieroplayer',
                launchArguments=['--player']
            ))

        # Remove HieroPlayer 11 from the list of versions found.
        filtered_applications = []
        for app in applications:
            if not app['version'].startswith('11.'):
                filtered_applications.append(app)

        self.logger.debug(
            'Discovered applications:\n{0}'.format(
                pprint.pformat(filtered_applications)
            )
        )

        return filtered_applications


def get_version_information(event):
    '''Return version information.'''
    return [
        dict(
            name='ftrack connect hieroplayer',
            version=ftrack_connect_hieroplayer.__version__
        )
    ]


def register(registry, **kw):
    '''Register hook for legacy plugins.'''

    logger = logging.getLogger(
        'ftrack_plugin:ftrack_connect_hieroplayer_hook.register'
    )

    # Validate that registry is an instance of ftrack.Registry. If not,
    # assume that register is being called from a new or incompatible API and
    # return without doing anything.
    if not isinstance(registry, ftrack.Registry):
        logger.debug(
            'Not subscribing plugin as passed argument {0!r} is not an '
            'ftrack.Registry instance.'.format(registry)
        )
        return

    applicationStore = ApplicationStore()

    ftrack.EVENT_HUB.subscribe(
        'topic=ftrack.action.discover and source.user.username={0}'.format(
            getpass.getuser()
        ),
        DiscoverApplicationsHook(applicationStore)
    )

    ftrack.EVENT_HUB.subscribe(
        'topic=ftrack.action.launch and source.user.username={0} '
        'and data.actionIdentifier={1}'.format(
            getpass.getuser(), ACTION_IDENTIFIER
        ),
        LaunchApplicationHook(
            ApplicationLauncher(applicationStore)
        )
    )

    ftrack.EVENT_HUB.subscribe(
        'topic=ftrack.connect.plugin.debug-information',
        get_version_information
    )