# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.cli.service_registry import get_service_registry
from google.adk.memory import VertexAiMemoryBankService

PROJECT_ID = "qwiklabs-gcp-01-eadc61e1e24e"
LOCATION = "us-east1"
MEMORY_BANK_ID = "4084569148955295744"

registry = get_service_registry()


def vertex_memory_factory(uri: str, **kwargs):
    return VertexAiMemoryBankService(
        project=PROJECT_ID,
        location=LOCATION,
        agent_engine_id=MEMORY_BANK_ID,
    )


registry.register_memory_service("memory", vertex_memory_factory)
