# Copyright 2012 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__author__ = 'Sean Lip'

import json
import unittest

from core.domain import exp_services
import feconf
import test_utils


@unittest.skipIf(feconf.PLATFORM != 'gae',
                 'login not implemented for non-GAE platform')
class EditorTest(test_utils.GenericTestBase):

    def test_editor_page(self):
        """Test access to editor pages for the sample exploration."""
        exp_services.delete_demo('0')
        exp_services.load_demo('0')

        # Check that non-editors cannot access the editor page.
        response = self.testapp.get('/create/0')
        self.assertEqual(response.status_int, 302)

        # Login as an admin.
        self.login('editor@example.com', is_admin=True)

        # Check that it is now possible to access the editor page.
        response = self.testapp.get('/create/0')
        self.assertEqual(response.status_int, 200)
        self.assertIn('Exploration Metadata', response.body)
        # Test that the value generator JS is included.
        self.assertIn('RandomSelector', response.body)

        self.logout()

    def test_add_new_state(self):
        """Test adding a new state to an exploration."""
        exp_services.delete_demo('0')
        exp_services.load_demo('0')

        # Login as an admin.
        self.login('editor@example.com', is_admin=True)

        response = self.testapp.get('/create/0')
        csrf_token = self.get_csrf_token_from_response(response)

        # Add a new state called 'New valid state name'.
        response_dict = self.post_json('/create/0/data', {
            'state_name': 'New valid state name', 'version': 1
        }, csrf_token)

        self.assertDictContainsSubset({'version': 2}, response_dict)
        self.assertTrue('stateData' in response_dict)
        self.assertDictContainsSubset(
            {'name': 'New valid state name'}, response_dict['stateData'])

        self.logout()

    def test_add_new_state_error_cases(self):
        """Test the error cases for adding a new state."""
        exp_services.delete_demo('0')
        exp_services.load_demo('0')

        # Login as an admin.
        self.login('editor@example.com', is_admin=True)

        response = self.testapp.get('/create/0')
        csrf_token = self.get_csrf_token_from_response(response)

        def _post_and_expect_400_error(payload):
            return self.post_json(
                '/create/0/data', payload, csrf_token,
                expect_errors=True, expected_status_int=400)

        # A POST request with no version number is invalid.
        response_dict = _post_and_expect_400_error({'state_name': 'New state'})
        self.assertIn('a version must be specified', response_dict['error'])

        # A POST request with the wrong version number is invalid.
        response_dict = _post_and_expect_400_error({
            'state_name': 'New state', 'version': 123})
        self.assertIn('which is too old', response_dict['error'])

        # A POST request with no state name is invalid.
        response_dict = _post_and_expect_400_error({'version': 1})
        self.assertIn('Please specify a state name.', response_dict['error'])

        # A POST request with an empty state name is invalid.
        response_dict = _post_and_expect_400_error({
            'state_name': '', 'version': 1})
        self.assertIn('Please specify a state name.', response_dict['error'])

        # A POST request with a state name containing invalid characters is
        # invalid.
        response_dict = _post_and_expect_400_error({
            'state_name': '[Bad State Name]', 'version': 1})
        self.assertIn('Invalid character [', response_dict['error'])

        # A POST request with a state name of feconf.END_DEST is invalid.
        response_dict = _post_and_expect_400_error({
            'state_name': feconf.END_DEST, 'version': 1})
        self.assertIn('Invalid state name', response_dict['error'])

        self.logout()


@unittest.skipIf(feconf.PLATFORM != 'gae',
                 'login not implemented for non-GAE platform')
class StatsIntegrationTest(test_utils.GenericTestBase):
    """Test statistics recording using the default exploration."""

    def test_state_stats_for_default_exploration(self):
        exp_services.delete_demo('0')
        exp_services.load_demo('0')

        # Check, from the editor perspective, that no stats have been recorded.
        self.login('editor@example.com', is_admin=True)

        response = self.testapp.get('/create/0/data')
        editor_exploration_dict = self.parse_json_response(response)
        self.assertEqual(editor_exploration_dict['num_visits'], 0)
        self.assertEqual(editor_exploration_dict['num_completions'], 0)

        # Switch to the reader perspective. First submit the first
        # multiple-choice answer, then submit 'blah'.
        response = self.testapp.get('/learn/0/data')
        exploration_dict = self.parse_json_response(response)
        self.assertEqual(exploration_dict['title'], 'Welcome to Oppia!')

        state_id = exploration_dict['state_id']
        response = self.testapp.post(str('/learn/0/%s' % state_id), {
            'payload': json.dumps({
                'answer': '0', 'block_number': 0, 'handler': 'submit',
                'state_history': exploration_dict['state_history'],
            })
        })
        exploration_dict = self.parse_json_response(response)
        state_id = exploration_dict['state_id']
        response = self.testapp.post(str('/learn/0/%s' % state_id), {
            'payload': json.dumps({
                'answer': 'blah', 'block_number': 0, 'handler': 'submit',
                'state_history': exploration_dict['state_history'],
            })
        })

        # Now switch back to the editor perspective.
        self.login('editor@example.com', is_admin=True)

        response = self.testapp.get('/create/0/data')
        editor_exploration_json = self.parse_json_response(response)
        self.assertEqual(editor_exploration_json['num_visits'], 1)
        self.assertEqual(editor_exploration_json['num_completions'], 0)

        # TODO(sll): Add more checks here.

        self.logout()


@unittest.skipIf(feconf.PLATFORM != 'gae',
                 'login not implemented for non-GAE platform')
class ExplorationDeletionRightsTest(test_utils.GenericTestBase):

    def setUp(self):
        """Creates dummy users."""
        super(ExplorationDeletionRightsTest, self).setUp()
        self.owner_id = 'owner@example.com'
        self.editor_id = 'editor@example.com'
        self.viewer_id = 'viewer@example.com'
        self.admin_id = 'admin@example.com'

    def test_deletion_rights_for_unpublished_exploration(self):
        """Test rights management for deletion of unpublished explorations."""
        UNPUBLISHED_EXP_ID = 'unpublished_eid'
        exp_services.create_new(
            self.owner_id, 'A title', 'A category', UNPUBLISHED_EXP_ID)

        exploration = exp_services.get_exploration_by_id(UNPUBLISHED_EXP_ID)
        exploration.editor_ids.append(self.editor_id)
        exp_services.save_exploration(self.owner_id, exploration)

        self.login(self.editor_id, is_admin=False)
        response = self.testapp.delete(
            '/create/%s/data' % UNPUBLISHED_EXP_ID, expect_errors=True)
        self.assertEqual(response.status_int, 401)
        self.logout()

        self.login(self.viewer_id, is_admin=False)
        response = self.testapp.delete(
            '/create/%s/data' % UNPUBLISHED_EXP_ID, expect_errors=True)
        self.assertEqual(response.status_int, 401)
        self.logout()

        self.login(self.owner_id, is_admin=False)
        response = self.testapp.delete('/create/%s/data' % UNPUBLISHED_EXP_ID)
        self.assertEqual(response.status_int, 200)
        self.logout()

    def test_deletion_rights_for_published_exploration(self):
        """Test rights management for deletion of published explorations."""
        PUBLISHED_EXP_ID = 'published_eid'
        exp_services.create_new(
            self.owner_id, 'A title', 'A category', PUBLISHED_EXP_ID)

        exploration = exp_services.get_exploration_by_id(PUBLISHED_EXP_ID)
        exploration.editor_ids.append(self.editor_id)
        exploration.is_public = True
        exp_services.save_exploration(self.owner_id, exploration)

        self.login(self.editor_id, is_admin=False)
        response = self.testapp.delete(
            '/create/%s/data' % PUBLISHED_EXP_ID, expect_errors=True)
        self.assertEqual(response.status_int, 401)
        self.logout()

        self.login(self.viewer_id, is_admin=False)
        response = self.testapp.delete(
            '/create/%s/data' % PUBLISHED_EXP_ID, expect_errors=True)
        self.assertEqual(response.status_int, 401)
        self.logout()

        self.login(self.owner_id, is_admin=False)
        response = self.testapp.delete(
            '/create/%s/data' % PUBLISHED_EXP_ID, expect_errors=True)
        self.assertEqual(response.status_int, 401)
        self.logout()

        self.login(self.admin_id, is_admin=True)
        response = self.testapp.delete('/create/%s/data' % PUBLISHED_EXP_ID)
        self.assertEqual(response.status_int, 200)
        self.logout()
