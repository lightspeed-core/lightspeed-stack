"""Quota management.

Tokens and token quota limits

Tokens are small chunks of text, which can be as small as one character or as
large as one word. Tokens are the units of measurement used to quantify the
amount of text that the service sends to, or receives from, a large language
model (LLM). Every interaction with the Service and the LLM is counted in
tokens.

LLM providers typically charge for their services using a token-based pricing model.

Token quota limits define the number of tokens that can be used in a certain
timeframe. Implementing token quota limits helps control costs, encourage more
efficient use of queries, and regulate demand on the system. In a multi-user
configuration, token quota limits help provide equal access to all users
ensuring everyone has an opportunity to submit queries.
"""
