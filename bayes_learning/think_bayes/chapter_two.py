import pandas as pd 
import numpy as np

'''
Bayes Theorem: 
P(A | B) = P(A)P(B | A) / P(B)

- Cookie Problem: 
    - Two bowls: 
        - Bowl One: 30 vanilla, 10 chocolate
        - Bowl Two: 20 vanilla, 20 chocolate
    - Choose cookie; if cookie is vanilla, what is the probability that it came from Bowl 1? 
    - Translates to: 
        P(B1 | V) = P(B1)P(V | B1) / P(V)
    - We want the term on the left
    - On the right: 
        - P(B1): probability we choose Bowl 1, not conditioned by the type of cookie
        - P(V | B1): probability of getting a vanilla cookie from Bowl 1, which is 3/4
        - P(V): probability of drawing a vanilla cookie from either bowl
    - Compute P(V) with law of total probability
        P(V) = P(B1)P(V | B1) + P(B2)P(V | B2)
        - Plug: P(V) = (1/2)(3/4) + (1/2)(1/2) = 5/8
        - This is the probability of choosing a vanilla cookie
    - Compute posterior probability of Bowl 1: 
        P(B1 | V) = (1/2)(2/4) / (5/8) = 3/5
- Diachronic Bayes
    - "diachronic": related to change over time
    - probability of the hypotheses changes as we see new data
    
'''