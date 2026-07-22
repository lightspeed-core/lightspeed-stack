"""Source to be tokenized."""

# # GenAI a Python
#
# Pavel Tišnovský,
# tisnik@centrum.cz
#
# ---
#
# ## Obsah
#
# * Teoretická část
#     - Strojové učení a umělá inteligence
#     - Modely, trénink, vyhodnocování
#     - Neuronové sítě
#     - Generativní umělá inteligence
#     - Frameworky pro GenAI
#     - Základní vlastnosti LLM
#     - OpenAI a další standardizovaná API
#     - Framework Llama Stack
#     - Langchain pro tvorbu aplikací využívajících GenAI
#     - RAG (Retrieval-augmented generation)
#     - Evaluace
# * Praktická část
#     - Volání LLM
#     - Langchain
#     - Tokenizace textu
#     - Tvorba embedded modelů
#     - Vyhledávání založené na podobnosti vektorů
#     - FAISS
#     - SentenceTransformer
#     - PgVector
#     - Závěrečný projekt
#
# ---
#
# # Teoretická část
#
# ---
#
# ## Úvod
#
# * Umělá inteligence
# * Vývoj umělé inteligence
# * Strojové učení
# * Vztah strojového učení a umělé inteligence
#
# ---
#
# ### Umělá inteligence
#
# * Definice
#     - konstrukce strojů, které dokážou provádět činnosti vyžadující inteligenci, pokud by byly prováděny lidmi (Marvin Minsky, 1967)
#     - existují ovšem i alternativní definice
# * Modelování lidské mysli
#     - shora dolů (psychologie)
#     - zdola nahoru (neurověda)
#     - zprostředka (informatika)
# * Inteligentní chování může vzniknout ze spojení velkého množství jednoduchých systémů
#     - koncept neuronových sítí
#
# ---
#
# ## Vývoj umělé inteligence
#
# * 1943-1955
#     - první myšlenky, že něco podobného může reálně vzniknout
#     - booleovský model neuronu
#     - A. Turing
#         - Computing Machinery and Intelligence
# * 1956
#     - McCarthy (LISP)
#     - (pravděpodobně) poprvé použil termín AI
#     - Newel a Simon: Logic theorist
# * velké očekávání pokroku v dalších letech
#     - dařilo se částečné řešení různých problémů
#     - prakticky každý měsíc nový objev
# * cca 1965
#     - vystřízlivění
#     - existovala sice spousta vyřešených problémů, ale ty byly triviální
#     - nalezeny limity, které se nedařilo překonat
#     - první "AI zima"
# * sedmdesátá léta
#     - systémy založené na znalostech
#     - vývoj v mnoha oblastech (hledání ropy atd.)
# * začátek osmdesátých let
#     - velké investice do AI
#     - očekávání se nenaplnila
#     - potom nastává druhá "AI zima"
# * druhá polovina osmdesátých let
#     - rozvoj neuronových sítí (což nebyla novinka)
# * 1995
#     - systémy SOAR (State, Operator and Result)
# * 2000
#     - big data (v tom pokračujeme i dnes)
#     - ale prozatím žádné větší objemy
#     - "wow" efekt na úrovni AI
# * 2010
#     - deep learning
# * 2020
#     - LLM (prompt engineering, ne fine tuning)
# * současnost
#     - LLM
#     - generativní AI
#
# ---
#
# ## Strojové učení
#
# * podoblast umělé inteligence
# * změna interního stavu systému při tréninku
# * několik způsobů realizace strojového učení
# * "statistické učení"
# * typicky se nejedná o plně automatizovanou činnost
#     - vyžaduje chytrá (strategická) rozhodnutí
#     - výběr modelu
#     - výběr hyperparametrů modelu
#     - rozdělení vstupních dat
#     - filtrace dat
# * nalézají se skryté vzorky a vazby v datech
#
# ---
#
# ## Vztah strojového učení a umělé inteligence
#
# ![vztah.png](images/ai_ml_dl.png)
#
# * Umělá inteligence (AI)
#     - strojové učení (machine learning, ML)
#     - hluboké učení (deep learning, DL)
#     - robotika
#     - neuronové sítě (NN)
#     - zpracování přirozeného jazyka (NLP)
# * AI > ML > NN > DL
#
# * Umělá inteligence
#     - objevování
#     - odvozování
#     - odůvodnění
# * Strojové učení
#     - (sofistikovaná) analýza
#     - predikce (!)
#     - rozhodování (klasifikace nebo regrese)
#
# ---
#
# ### Proč strojové učení?
#
# * Chceme, aby se stroj naučil řešit zadaný problém na základě vzorových řešení:
#     - řešení je příliš komplikované
#     - problém se často mění, vyvíjí
#     - lidská práce je drahá (v porovnání se strojovou)
#     - máme k dispozici tolik dat, že je není možné zpracovat "ručně"
#
# ---
#
# ### Typické aplikace strojového učení
#
# * Rozpoznávání vzorů
#     - věci/osoby/výrazy tváře na fotkách
#     - mluvená slova
#     - spam
#     - medicínská diagnóza
# * Rozpoznávání anomálií
#     - netypické sekvence finančních transakcí
#     - netypická data přicházející ze senzorů v atomové elektrárně
# * Předpovídání
#     - vývoj ceny akcií na burze / vývoj měnového kurzu
#     - jaké filmy bude mít daný člověk rád
#     - věk osoby na fotografii
# * Shlukování
#     - vyhledávání zpráv s podobným obsahem
#     - vyhledání skupin zákazníků s podobnými vlastnostmi
#
# ---
#
# ## Základní pojmy
#
# * Datová sada
#     - trénovací data
#     - testovací data
#
# ![dataset.png](images/dataset.png)
#
# ---
#
# ### Techniky strojového učení
#
# * Supervised learning
#     - také se nazývá "predictive modeling"
#     - známe takzvané "kategorie" neboli odpovědi
# * Unsupervised learning
#     - neznáme odpovědi
#     - model musí najít struktury/vzory v datech
#     - typicky různé varianty clusteringu
#
# ![ml.png](images/ml.png)
#
# ---
#
# ### Supervised learning
#
# 1. trénink na základě vstupních dat
#     - model se naučí vztahy mezi daty a očekávanou odpovědí
# 2. predikce na základě jiných(!) dat
#     - problematika rozdělení dat
# 3. výsledky
#     - klasifikace: koupí si A, B nebo C?
#     - regrese: vektor příznaků, numerická hodnota nebo hodnoty
#
# ---
#
# ### Unsupervised learning
#
# 1. trénink modelu na základě vstupních dat
#     - ovšem bez znalosti správných odpovědí
# 2. shluková analýza
# 3. latentní a faktorová analýza
#
# ---
#
# ### Další možnosti
#
# 1. kombinace obou metod (bez/s učitelem)
# 2. učení se zpětnou vazbou
#     - pasivní
#     - aktivní
#
# ---
#
# ### Modely strojového učení
#
# * ANN
# * Desicion trees
# * Support-vector machine
# * Regresní analýza
# * Bayesovské sítě
# * Genetické algoritmy
# * Neuronové sítě
#
# ---
#
# ### Jak začít?
#
# 1. jaké atributy použít z dat?
# 2. jaký model vybrat
# 3. jak optimalizovat pro větší výkon
# 4. jak vytvořit model, který bude vhodný pro pro něj neznámá data?
# 5. jak odhadnout vhodnost modelu pro neznámá data?
#
# ---
#
# ### Komprimace dat
# * souvislost mezi ML a komprimací dat
# * predikce
# * tzv. optimální komprese
#     - při predikci lze použít aritmetické kódování
#
# ---
#
# ### Redukce dat
#
# ![reduction.png](images/reduction.png)
#
# ---
#
# ### Redukce dat
#
# ![reduction_supervised.png](images/reduction_supervised.png)
#
# ---
#
# ### Nedoučení a přeučení
#
# * Nedoučení
#     - malá sada dat, na kterých je model trénován
#     - příliš složitý model
#     - data reprezentují pouze malý vzorek celého spektra hodnot
# * Přeučení
#     - velká vazba na trénovací data
#     - menší flexibilita práce s daty, která model nezná
#     - použití polynomu vyššího stupně, když by stačila lineární regrese
#
# ---
#
# ### Přeučení
#
# ![overtrain.png](images/overtraining.png)
#
# ---
#
# ### Úspěšnost modelu
#
# * Pro zcela nová (neznámá) data!
#     - ne pro trénovací množinu
#     - častá chyba
#
# ---
#
# ### Křížová validace (cross validation)
#
# * rozdělení dat do bloků
#     - například na 1/10
#     - 9/10 pro trénink
#     - 1/10 pro otestování
#
# ---
#
# ## Neuronové sítě
#
# * Propojení takzvaných neuronů
#     - Model neuronu
#     - Způsob propojení neuronů
#     - Vstupy a výstupy
#
# ---
#
# ### Model neuronu
#
# ![neuron.png](images/neuron.png)
#
# * libovolný počet vstupů
# * typicky jeden výstup
# * váhy vstupů
# * aktivační funkce
#
# y = f(w1x1 + w2x2 + … + wnxn)
#
# ---
#
# ### Bias
#
# ![bias.png](images/bias.png)
#
# y = f(w0 + w1x1 + w2x2 + … + wnxn)
#
# ---
#
# ### Aktivační funkce
#
# * Jediná nelinearita v modelu
# * Mnoho typů aktivačních funkcí
#
# ---
#
# ### Aktivační funkce
#
# ![akt1.png](images/akt_1.png)
#
# ---
#
# ### Aktivační funkce
#
# ![akt2.png](images/akt_2.png)
#
# ---
#
# ### Feed-forward síť
#
# * Vstupní vrstva
# * Skryté vrstvy
# * Výstupní vrstva
#
# ---
#
# ### Feed-forward síť
#
# ![ff.png](images/ff.png)
#
# ---
#
# ### Příliš mnoho vrstev
#
# * Model se přestane učit nebo se učí velmi pomalu
#     - vanishing gradient problem
#     - "méně je někdy více"
#
# ---
#
# ### Konvoluční neuronové sítě
#
# * Typicky pro rastrové obrázky
#     - mírné posunutí, zkosení atd.
#     - lze sice řešit klasickými NN
#     - ovšem je to zbytečně složité (RAM, CPU, čas)
#     - příliš mnoho stejných, ale samostatně uložených vah
#     - konvoluční a subsamplingové vrstvy
#
# ---
#
# ### Konvoluční neuronové sítě
#
# * Typická konfigurace
#     - vstupní vrstva
#     - konvoluční vrstva #1
#     - subsamplingová vrstva #1
#
# ---
#
# # Generativní AI
#
# ![LS](images/lsc.jpg)
#
# ---
#
# ## Frameworky pro GenAI
# * langchain
# * langgraph
# * autogen
# * metaGPT
# * phidata
# * CrewAI
# * pydanticAI
# * controlflow
# * langflow
# * LiteLLM (???)
# * Llama Stack
#
# ---
#
# ## Potřebujeme sofistikované frameworky?
#
# * některé základní operace je možné provést i jen s využitím "pouhých" knihoven
# * příkladem může být knihovna OpenAI
# * a do určité míry taktéž LiteLLM

#
# ---
#
# ### Výpis všech dostupných modelů
# - používá se přímo balíček openai
# - klíč se získává z proměnné prostředí

import os
import uuid
from pathlib import Path

from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from ogx.core.library_client import OGXAsLibraryClient
from ogx_client import OgxClient
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
models = client.models.list()

for model in models:
    print(model.id)

# ---
#
# ## Potřebujeme sofistikované frameworky?
#
# * Kvóty
# * Konverzace
# * Kontext
# * Guardrails
# * RAG
# * BYOK
# * MCP
# * Agenti
# * A2A
#
# ---
#
# ## Llama Stack
#
# ![Llama Stack logo](images/llama_stack_logo.png)
#
# ---
#
# ## Co je to Llama Stack?
#
# * Framework pro tvorbu aplikací s AI
#     - chat boti
#     - obecně generativní AI (GenAI)
#     - trénink, evaluace
# * Skutečný framework nezávislý na programovacím jazyku
#     - systém providerů
#     - RAG, správa kvóty, guardrails, metriky atd.
#
# ---
#
# ### Nejjednodušší využití Llama Stacku
#
# * Volání LLM
# * Zpracování odpovědi od LLM
# * "chatbot v.0.0.1"
#
# ---
#
# ### Skutečné požadavky jsou však širší
#
# * Podpora RAG
# * Historie konverzace
# * Rozvětvení konverzace
# * Zapamatování fakt o uživateli
# * Volání MCP
# * Kvóty
# * Kontrola dotazů a odpovědí
# * Volání více LLM, evaluace odpovědí atd.
#
# ---
#
# ### API a poskytovatelé
#
# * Plně konfigurovatelné
# * Lze získat seznam dostupných API
# * Taktéž lze získat seznam dostupných poskytovatelů
# * Pozor: závislosti vyžadované jednotlivými poskytovateli
#
# ---
#
# ![Providers](images/llama_stack_providers.png)
#
# ### Poskytovatelé
#
# * Agents
#     - interakce se systémem agentů (samotní agenti mohou provádět různé operace)
# * Inference
#     - rozhraní k&nbsp;LLM modelům i k embedding modelům
# * VectorIO
#     - původně rozhraní k vektorovým databázím (hledání podobných vektorů)
#     - nyní i fulltext hledání
# * Safety
#     - detekce dotazů s nevhodným či nepovoleným obsahem apod.
# * Telemetry
#     - telemetrie
#     - OpenTelemetry ale i další
# * Eval
#     - vyhodnocování odpovědí modelů atd.
# * DatasetIO
#     - čtení a zápisy datových sad z/do zvoleného systému
#     - může být i lokální souborový systém
#
# ---
#
# ### Komunikace s Llama Stackem
#
# * CLI
# * REST API
# * Jako běžná knihovna (Python atd.)
# * Llama Stack klient
#     - podporuje REST API
#     - podporuje i běh formou knihovny (async)
#
# ---
#
# ### Llama Stack klient
#
# * Python
# * Swift
# * Kotlin
# * Node.js
#
# ---
#
# ### Llama Stack jako knihovna
#
# ![LS1](images/llama_stack_as_library.png)
#
# ---
#
# ### Llama Stack jako samostatná služba
#
# ![LS1](images/llama_stack_as_service.png)
#
# ---
#
# ### Běh v kontejneru
#
# ![LS1](images/llama_stack_in_container.png)
#
# ---
#
# ### Příklad služby postavené na Llama Stacku
#
# * REST API postavené nad API Llama Stacku
# * Obě možnosti spuštění Llama Stacku
# * Implementace formou asynchronního kódu (Python)
#
# ---
#
# ![LS1](images/llama_stack_arch.png)
#
# ---
#
# ![Langchain logo](images/langchain.png)
#
# ---
#
# ### Langchain
#
# * Framework pro GenAI a Python
# * Chatboti
# * RAG
# * Paměť konverzací
# * Shrnutí konverzací
# * Generování syntetických dat
#
# ---
#
# ### Langchain
#
# * Jednoduché úkoly je možné řešit jednoduše
# * Mnohdy pouze několikařádkové skripty
# * Operátor | pro tvorbu "kolon"
# * Napojení na RAG
#
#
# ---
#
# ## Evaluace
#
# ### Proč provádět evaluaci?
#
# * Celková výkonnost
# * Uživatelská zkušenost
# * Detekce zkreslení odpovědí
# * Dodržování etických a právních předpisů
#
# ### Přednosti
#
# * Zlepšení odpovědí
#     - detekce halucinací atd.
# * Ladění modelu řízené daty
# * Benchmarky
#     - porovnání modelů (GPT, Gemini, Granite, etc.)
# * Zlepšení spolehlivosti v průběhu času
#
# ### Lightspeed evaluation framework
#
# * Podpora více LLM
#     - Ragas, DeepEval + vlastní implementace
# * Evaluace celé konverzace
# * Podpora nástrojů (tools) a agentů
# * Závěrečná statistická analýza
# * LLM provideři
#       - OpenAI, Watsonx, Gemini, vLLM and others
# * Skripty pro setup a cleanup
# * Statistická analýza
#
# ---
#
# # Praktická část
#
# ![Work](images/work.jpg)
#
# - Volání LLM
# - Langchain
# - Tokenizace textu
# - Tvorba embedded modelů
# - Vyhledávání založené na podobnosti vektorů
# - PgVector
# - FAISS
# - Evaluace
#
# ---
#
# ### Llama Stack klient
#
# * Využijeme klienta pro Python
#
# ```bash
# uv init
# uv add llama-stack-client
# ```
#
# ---
#

#
# ### Llama Stack běží jako samostatná služba
#

# Získání seznamu všech dostupných modelů


client = OgxClient(base_url="http://localhost:8321")

print(f"Using Llama Stack version {client._version}")

models = client.models.list()

for model in models:
    print(model)

# ---
#
# ### Llama Stack je použit jako běžná knihovna
#

# Získání seznamu všech dostupných modelů


client = OGXAsLibraryClient("run.yaml")
client.initialize()

print(f"Using Llama Stack version {client._version}")

models = client.models.list()

for model in models:
    print(model)

# ---
#
# ### Komunikace s LLM

client = OgxClient(base_url="http://localhost:8321")

print(f"Using Llama Stack version {client._version}")

models = client.models.list()
model_id = models[0].identifier

print(f"Using model {model_id}")

response = client.chat.completions.create(
    model=model_id,
    messages=[{"role": "user", "content": "What is the capital of France?"}],
)

print(response.to_json())

# ---
#
# ### Vývoj Llama Stacku
#
# * Změny v API
# * Plány na ukončení podpory starších API
#     - deprecation
# * Náhrada agent API za OpenAI API
# * Stabilizace ve verzi 0.7.0 ???
#
# ---

# ### Využití novějšího API

client = OgxClient(base_url="http://localhost:8321")

print(f"Using Llama Stack version {client._version}")

models = client.models.list()
model_id = models[0].identifier

print(f"Using model {model_id}")

response = client.chat.completions.create(
    model=model_id,
    messages=[{"role": "user", "content": "What is the capital of France?"}],
)

print(response.to_json())

# ---
#
# ### Získávání informací z poskytnutých dokumentů
#
# * RAG
# * Ovšem i další vstupy
#     - sémantické vyhledávání
#     - fulltext vyhledávání
#     - hybridní vyhledávání
#
# ---
#

# ### Prvotní zpracování dokumentů

# * připojení k Llama Stacku
# * vytvoření nové vektorové databáze
# * inicializace vektorové databáze

client = OgxClient(base_url="http://localhost:8321")
print(f"Using Llama Stack version {client._version}")

vector_store_name = f"vec_{str(uuid.uuid4())[0:8]}"
print(f"Vector store name: {vector_store_name}")

vector_store = client.vector_stores.create(name=vector_store_name)
vector_store_id = vector_store.id

print(f"Vector store ID: {vector_store_id}")

# * nyní již můžeme do databáze přidat obsah textového souboru nebo jiného dokumentu
path = Path("cesta_k_souboru.md")
print(f"File path: {path}")

file_create_response = client.files.create(file=path, purpose="assistants")
print(f"File create response: {file_create_response}")

file_ingest_response = client.vector_stores.files.create(
    vector_store_id=vector_store_id,
    file_id=file_create_response.id,
)
print(f"File ingest response: {file_ingest_response}")

# * textový dokument je v této chvíli již zpracován
# * získání odpovědi z dokumentu

models = client.models.list()
model_id = models[0].identifier
model_provider = models[0].identifier

print(f"Using model {model_id}")

MODEL_ID = "openai/gpt-4-turbo"


def print_rag_response(response):
    """Pomocná funkce pro tisk celé odpovědi."""
    print(f"ID: {response.id}")
    print(f"Status: {response.status}")
    print(f"Model: {response.model}")
    print(f"Created at: {response.created_at}")
    print(f"Output items: {len(response.output)}")

    for i, output_item in enumerate(response.output):
        if len(response.output) > 1:
            print(f"\n--- Output Item {i+1} ---")
        print(f"Output type: {output_item.type}")

        if output_item.type in ("text", "message"):
            print(f"Response content: {output_item.content[0].text}")
        elif output_item.type == "file_search_call":
            print(f"  Tool Call ID: {output_item.id}")
            print(f"  Tool Status: {output_item.status}")
            print(f"  Queries: {', '.join(output_item.queries)}")
            print(
                f"  Results: {output_item.results if output_item.results else 'None'}"
            )
        else:
            print(f"Response content: {output_item.content}")


# získání odpovědi s využitím vektorové databáze

response = client.responses.create(
    model=MODEL_ID,
    input="zadaný dotaz",
    tools=[
        {
            "type": "file_search",
            "vector_store_ids": [vector_store_id],
        }
    ],
)

print_rag_response(response)

# ---
#
# ### Ukázka 1/2
#
# * Dokument:
#     - `README.TXT` ze hry Supaplex
# * Relevantní část z dokumentu:
#
# ```plaintext
# [a round rock] - ZONK
#        This is another very common obstacle (and usually a very
#        unpleasant one) a Zonk tends to fall down whenever possible
#        (i.e. there is a void underneath). Be careful, when a Zonk
#        falls on you (Murphy) you will explode (read: die). Murphy can
#        push Zonks to the side (not up and down) if nothing is blocking
#        the Zonk (i.e. there is a void on the other side). Murphy can
#        only push one Zonk at a time, so watch out when dropping Zonks
#        next to each other! With some good timing, you can also drop
#        Zonks on Electrons (see below) or Snik-snaks (see below) which
#        will explode (and not bother you again). Zonks have the nasty
#        habit of falling SIDEWAYS off Ram-Chips (see below) and other
#        Zonks if possible (i.e. there is a void to the side), on all
#        other objects the Zonks will lie steady.
# ```
#
# ---
#
# ### Ukázka 2/2
# * Dotaz:
# ```plaintext
# What is Zonk?
# ```
# * Odpověď:
# ```plaintext
# "ZONK" refers to an element in the videogame Supaplex. In the
# game, a Zonk is depicted as a round rock, and it is a common and typically
# unpleasant obstacle. Zonks tend to fall downwards whenever possible, for
# instance, if there is a void directly underneath them. Players must be cautious
# as a Zonk falling on the character (Murphy) results in an explosion and
# game-over for the player. Murphy can push Zonks laterally (but not vertically)
# if there is space for them to move, but can only push one Zonk at a time. Good
# timing is needed to use Zonks strategically, such as dropping them on top of
# enemies (like Snik-snaks) to eliminate them through explosions.
# ```
#
# ---
#
# ### Současná situace okolo Llama Stacku
#
# * Meta -> vLLM
# * Zaměření na kompatibilitu s Responses API (OpenAI)
# * Podpora pro agentic flow (ovšem jen základní)
# * Postupně se některé další funkce odstraňují (!)
# * Výsledkem je nestabilita celé platformy
# * Pokud vyvíjíte stabilní projekt, je Llama Stack riziko
#
# ---
#
# ![Langchain logo](images/langchain.png)
#
# * začneme jednoduchými příklady, které postupně rozšíříme
# * poslední příklad bude odpovídat příkladu z Llama Stacku
#    - odpovědi
#    - RAG

# ---

# ### Získání odpovědi z LLM
# - inicializace rozhraní k modelu poskytovaného přes OpenAI
# - poslání dotazu do jazykového modelu
# - tisk odpovědi


llm = ChatOpenAI(model_name="gpt-4o-mini")
response = llm.invoke("Say Hi")
print(response)


# ### Objekt typu `response`
# - inicializace rozhraní k modelu poskytovaného přes OpenAI
# - poslání dotazu do jazykového modelu
# - tisk odpovědi v naformátované podobě


llm = ChatOpenAI(model_name="gpt-4o-mini")
response = llm.invoke("Say Hi")
print(response)

# ### Nastavení "teploty"
# - inicializace rozhraní k modelu poskytovaného přes OpenAI
# - nastavení parametrů jazykového modelu
# - poslání dotazu do jazykového modelu
# - tisk odpovědi


llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7)
response = llm.invoke("Say Hi")
print(response)

# ### Koncept šablon
# - konstrukce jednoduchého řetězce
# - předání parametru do výzvy
# - poslání dotazu do jazykového modelu
# - tisk odpovědi


prompt = PromptTemplate.from_template("How to say 'hi' in {language} language?")

llm = ChatOpenAI(model_name="gpt-4o-mini")
chain = LLMChain(prompt=prompt, llm=llm)

response = chain.invoke("Czech")
print(response)

# ### Řetězce (kolony)
# - jednoduchý řetězec
# - nastavení parametrů jazykového modelu
# - poslání dotazu do jazykového modelu
# - tisk odpovědi


prompt = PromptTemplate(
    input_variables=["language"],
    template="How to say 'hi' in {language} language?",
)


llm = ChatOpenAI(model_name="gpt-4o-mini")
chain = LLMChain(prompt=prompt, llm=llm)

response = chain.invoke("Czech")
print(response)

# ### Řetězce (kolony)
# - jednoduchý řetězec vytvořený operátorem |
# - nastavení parametrů jazykového modelu
# - poslání dotazu do jazykového modelu
# - tisk odpovědi

prompt = PromptTemplate.from_template("How to say 'hi' in {language} language?")

llm = ChatOpenAI(model_name="gpt-4o-mini")

chain = prompt | llm | StrOutputParser()

response = chain.invoke({"language": "Czech"})
print(response)
