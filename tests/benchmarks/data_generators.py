"""Data generators used by benchmarks."""

import random


def generate_provider() -> str:
    """Return a randomly chosen provider name.

    The provider is selected from a predefined list of possible providers to
    simulate different user conversation during benchmarks.

    Returns:
        str: Selected provider name.
    """
    providers = [
        "openai",
        "azure",
        "vertexAI",
        "watsonx",
        "RHOAI (vLLM)",
        "RHAIIS (vLLM)",
        "RHEL AI (vLLM)",
    ]
    return random.choice(providers)


def generate_model_for_provider(provider: str) -> str:
    """Return a randomly chosen model ID for a given provider.

    Parameters:
        provider (str): Name of the provider for which to pick a model.

    Returns:
        str: A model identifier associated with the given provider. If the
            provider is unknown, a fallback value of "foo" is returned.
    """
    models: dict[str, list[str]] = {
        "openai": [
            "gpt-5",
            "gpt-5.2",
            "gpt-5.2 pro",
            "gpt-5 mini",
            "gpt-4.1",
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-4.1 mini",
            "gpt-4.1 nano",
            "o4-mini",
            "o1",
            "o3",
            "o4",
        ],
        "azure": [
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
            "gpt-4.1",
            "gpt-4.1 mini",
            "gpt-5-chat",
            "gpt-5.1",
            "gpt-5.1-codex",
            "gpt-5.2",
            "gpt-5.2-chat",
            "gpt-5.2-codex",
            "claude-opus-4-5",
            "claude-haiku-4-5",
            "claude-sonnet-4-5",
            "DeepSeek-v3.1",
        ],
        "vertexAI": [
            "google/gemini-2.0-flash",
            "google/gemini-2.5-flash",
            "google/gemini-2.5-pro",
        ],
        "watsonx": [
            "all-mini-l6-v2",
            "multilingual-e5-large",
            "granite-embedding-107m-multilingual",
            "ibm-granite/granite-4.0-micro",
            "ibm-granite/granite-4.0-micro-base",
            "ibm-granite/granite-4.0-h-micro",
            "ibm-granite/granite-4.0-h-micro-base",
            "ibm-granite/granite-4.0-h-tiny",
            "ibm-granite/granite-4.0-h-tiny-base",
            "ibm-granite/granite-4.0-h-small",
            "ibm-granite/granite-4.0-h-small-base",
            "ibm-granite/granite-4.0-tiny-preview",
            "ibm-granite/granite-4.0-tiny-base-preview",
        ],
        "RHOAI (vLLM)": ["meta-llama/Llama-3.2-1B-Instruct"],
        "RHAIIS (vLLM)": ["meta-llama/Llama-3.1-8B-Instruct"],
        "RHEL AI (vLLM)": ["meta-llama/Llama-3.1-8B-Instruct"],
    }
    return random.choice(models.get(provider, ["foo"]))


def generate_topic_summary() -> str:
    """Return a randomized topic summary string.

    The summary is constructed by selecting one phrase from each of several
    phrase groups to create varied but deterministic-looking summaries for the
    test data.

    Returns:
        str: Generated summary sentence ending with a period.
    """
    yaps = [
        [
            "Soudruzi,",
            "Na druhe strane",
            "Stejne tak",
            "Nesmime vsak zapominat, ze",
            "Timto zpusobem",
            "Zavaznost techto problemu je natolik zrejma, ze",
            "Kazdodenni praxe nam potvrzuje, ze",
            "Pestre a bohate zkusenosti",
            "Poslani organizace, zejmena pak",
            "Ideove uvahy nejvyssiho radu a rovnez",
        ],
        [
            "realizace planovanych vytycenych ukolu",
            "ramec a mista vychovy kadru",
            "stabilni a kvantitativni vzrust a sfera nasi aktivity",
            "vytvorena struktura organizace",
            "novy model organizacni cinnosti",
            "stale, informacne-propagandisticke zabezpeceni nasi prace",
            "dalsi rozvoj ruznych forem cinnosti",
            "upresneni a rozvoj struktur",
            "konzultace se sirokym aktivem",
            "pocatek kazdodenni prace na poli formovani pozice",
        ],
        [
            "hraje zavaznou roli pri utvareni",
            "vyzaduji od nas analyzy",
            "vyzaduji nalezeni a jednoznacne upresneni",
            "napomaha priprave a realizaci",
            "zabezpecuje sirokemu okruhu specialistu ucast pri tvorbe",
            "ve znacne mire podminuje vytvoreni",
            "umoznuje splnit vyznamne ukoly na rozpracovani",
            "umoznuje zhodnotit vyznam",
            "predstavuje pozoruhodny experiment proverky",
            "vyvolava proces zavadeni a modernizace",
        ],
        [
            "existujicich financnich a administrativnich podminek",
            "dalsich smeru rozvoje",
            "systemu masove ucasti",
            "pozic jednotlivych ucastniku k zadanym ukolum",
            "novych navrhu",
            "systemu vychovy kadru odpovidajicich aktualnim potrebam",
            "smeru progresivniho rozvoje",
            "odpovidajicich podminek aktivizace",
            "modelu rozvoje",
            "forem pusobeni",
        ],
    ]

    summary = " ".join([random.choice(yap) for yap in yaps]) + "."
    return summary
