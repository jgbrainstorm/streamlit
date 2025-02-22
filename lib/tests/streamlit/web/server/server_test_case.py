# Copyright 2018-2022 Streamlit Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import urllib.parse
from asyncio import Future
from unittest import mock

import tornado.testing
import tornado.web
import tornado.websocket
from tornado.websocket import WebSocketClientConnection

from streamlit.runtime.app_session import AppSession
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg
from streamlit.web.server import Server


class ServerTestCase(tornado.testing.AsyncHTTPTestCase):
    """Base class for async streamlit.server testing.

    Subclasses should patch 'streamlit.server.server.AppSession',
    to prevent AppSessions from being created, and scripts from
    being run. (Script running involves creating new threads, which
    interfere with other tests if not properly terminated.)

    See the "ServerTest" class for example usage.
    """

    _next_session_id = 0

    def get_app(self) -> tornado.web.Application:
        self.server = Server(
            "/not/a/script.py",
            "test command line",
        )
        app = self.server._create_app()
        return app

    async def start_server_loop(self) -> None:
        """Starts the server's loop coroutine."""
        server_started = Future()
        self.io_loop.spawn_callback(
            self.server._loop_coroutine, lambda _: server_started.set_result(None)
        )
        await server_started

    def get_ws_url(self, path):
        """Return a ws:// URL with the given path for our test server."""
        # get_url() gives us a result with the 'http' scheme;
        # we swap it out for 'ws'.
        url = self.get_url(path)
        parts = list(urllib.parse.urlparse(url))
        parts[0] = "ws"
        return urllib.parse.urlunparse(tuple(parts))

    async def ws_connect(self) -> WebSocketClientConnection:
        """Open a websocket connection to the server.

        Returns
        -------
        WebSocketClientConnection
            The connected websocket client.

        """
        return await tornado.websocket.websocket_connect(self.get_ws_url("/stream"))

    async def read_forward_msg(
        self, ws_client: WebSocketClientConnection
    ) -> ForwardMsg:
        """Parse the next message from a Websocket client into a ForwardMsg."""
        data = await ws_client.read_message()
        message = ForwardMsg()
        message.ParseFromString(data)
        return message

    @staticmethod
    def _create_mock_app_session(*args, **kwargs):
        """Create a mock AppSession. Each mocked instance will have
        its own unique ID."""
        mock_id = mock.PropertyMock(
            return_value=f"mock_id:{ServerTestCase._next_session_id}"
        )
        ServerTestCase._next_session_id += 1

        mock_session = mock.MagicMock(AppSession, autospec=True, *args, **kwargs)
        type(mock_session).id = mock_id
        return mock_session

    def _patch_app_session(self):
        """Mock the Server's AppSession import. We don't want
        actual sessions to be instantiated, or scripts to be run.
        """

        return mock.patch(
            "streamlit.web.server.server.AppSession",
            # new_callable must return a function, not an object, or else
            # there will only be a single AppSession mock. Hence the lambda.
            new_callable=lambda: self._create_mock_app_session,
        )
