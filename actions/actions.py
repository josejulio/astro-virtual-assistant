# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions

from typing import Any, Text, Dict, List, Optional
from os import getenv

from rasa_sdk import Action, Tracker
from rasa_sdk.types import DomainDict
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import ActionExecuted, EventType, SlotSet
import requests
import random
import math

from .auth import get_auth_token
from .forms import IntentBasedFormValidationAction


CONSOLEDOT_BASE_URL = "https://console.redhat.com"

people_talked_to: int = math.floor(random.random() * 2000000)

# once we have metrics on number of responses in one day,
# have the VA report on people talked to, number of responses, etc.
class BotMetrics(Action):

    def name(self) -> Text:
        return 'action_bot_metrics'

    async def run(self,
                  dispatcher: CollectingDispatcher,
                  tracker: Tracker,
                  domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        global people_talked_to

        people_talked_to = people_talked_to + 1

        dispatcher.utter_message(text="Well, it's been a long shift. I've talked to {} people and you!".format(people_talked_to))

        events = [ActionExecuted(self.name())]
        return events


class ConsoleAPIAction(Action):

    def name(self) -> Text:
        return 'action_console_api'

    async def run(self,
                  dispatcher: CollectingDispatcher,
                  tracker: Tracker,
                  domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        base_url = getenv("CONSOLEDOT_BASE_URL", CONSOLEDOT_BASE_URL)
        token = get_auth_token(tracker)

        result = None

        try:
            result = requests.get(
                base_url+"/api/vulnerability/v1/systems",
                headers={"Authorization": "Bearer " + token}
            ).json()
        except Exception as e:
            print(f"An Exception occured while handling response from the Vulnerability API: {e}")

        if not result or not result['meta']:
            dispatcher.utter_message(text="I was Unable to retrieve systems.")
            return []

        dispatcher.utter_message(text="You have {} systems, listing first {}:".format(result['meta']['total_items'], len(result['data'])))

        for system in result['data']:
            dispatcher.utter_message(text="{} ({}) has {} active CVEs. You can get more details on: {}".format(
                system['attributes']['display_name'],
                system['attributes']['os'],
                system['attributes']['cve_count'],
                base_url+"/insights/vulnerability/systems/{}".format(system['id'])
            ))

        events = [ActionExecuted(self.name())]
        return events


class OpenshiftCreateClusterAction(IntentBasedFormValidationAction):

    def name(self) -> Text:
        return "validate_form_openshift_clusters_create-cluster"

    def utter_not_extracted(self, slot_name: Text) -> Optional[Text]:
        return "Sorry, I didn't understand. Can you rephrasing your answer?"

    def form_finished(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict, result: List[EventType]):
        slots = tracker.slots
        is_managed_and_hosted = slots.get("openshift_managed") == "yes" and slots.get("openshift_hosted") == "hosted"
        is_on_cloud = slots.get("openshift_where") == "cloud"
        provider = slots.get("openshift_provider")

        found = False

        if is_managed_and_hosted and is_on_cloud:
            base_response = "Great, thanks for that information. I recommend using "
            if provider == "aws":
                dispatcher.utter_message(text=base_response + "Red Hat OpenShift Service on AWS (ROSA).")
                found = True
            elif provider == "azure":
                dispatcher.utter_message(text=base_response + "Azure Red Hat Openshift")
                found = True

        if not found:
            dispatcher.utter_message(text="Great, thanks for that information. I recommend using X.")

        dispatcher.utter_message(text=f"""Your answers:
 - Where: {slots.get('openshift_where')}
 - Provider: {slots.get('openshift_provider')}
 - Managed by Red Hat: {slots.get('openshift_managed')}
 - Hosted or Standalone control plane?: {slots.get('openshift_hosted')}""")

        # Clear slots
        result.append(SlotSet('openshift_where', None))
        result.append(SlotSet('openshift_provider', None))
        result.append(SlotSet('openshift_managed', None))
        result.append(SlotSet('openshift_hosted', None))

    async def extract_openshift_hosted(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict):
        next_slot = (await self.next_requested_slot(dispatcher, tracker, domain)).get("value")
        value = None

        if next_slot == "openshift_hosted":
            message = tracker.latest_message.get("text").lower()
            # Todo: Replace with embeddings
            if "standalone" in message:
                value = "standalone"
            elif "hosted" in message:
                value = "hosted"

        return {
            "openshift_hosted": value
        }

    async def required_slots(
            self,
            domain_slots: List[Text],
            dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: DomainDict
    ) -> List[Text]:
        base_slots = [
            "openshift_where",
            "openshift_provider",
            "openshift_managed",
            "openshift_hosted"
        ]

        if tracker.slots.get("openshift_where") != "cloud":
            base_slots.remove("openshift_provider")

        return base_slots
