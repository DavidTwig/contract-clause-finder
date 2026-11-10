# Manual review pack (eval)

For each case, reply with: **number: model error / gold label issue / ambiguous, short note**.

Source: `results/eval.json` (eval attempt 2, complete) and `data/contracts.jsonl`. Built by `scripts/review_pack.py`; no API calls. Definitions are CUAD's (`category_definitions_v4`). Spaces and blank lines in contract text are collapsed for reading only. In the context, »…« marks the passage the case is about. Selection rules are in the script docstring.

Cap on Liability gold spans missed in Verified contracts: 6 in total, in 2 contracts; 3 are included, taken from each contract in turn.

---

## A. Termination for Convenience: Verified, no CUAD gold

### Case 1: Termination for Convenience, AgapeAtpCorp_20191202_10-KA_EX-10.1_11911128_EX-10.1_Supply Agreement

**Status shown:** Verified

**CUAD definition:** Can a party terminate this contract without cause (solely by giving a notice and allowing a waiting period to expire)?

**Model's quote:**
> A six (6) months notice must be given by either party of their intention to terminate relations due to any reason other than breach of this agreement.

**Model's reason:** Specifies notice period to end contract without cause.

**Second review (confirm):** The clause allows either party to end the contract without cause by giving six months' notice.

**CUAD's marked text for this type** (0 spans):
> (none)

**Surrounding contract text:**
> …agreement will be automatically renewed at the end of every ten (10) year term, with each subsequent term of renewal being for a ten (10) year term. »A six (6) months notice must be given by either party of their intention to terminate relations due to any reason other than breach of this agreement.« ODM Supply Agreement 2 Organic Preparations INC. & Agape ATP International Holding Limited
> Source: AGAPE ATP CORP, 10-K/A, 12/2/2019
> 2. PROVISI…

**Your label:** ______  **Note:** ______

### Case 2: Termination for Convenience, GALERATHERAPEUTICS,INC_02_14_2020-EX-99.A-JOINT FILING AGREEMENT

**Status shown:** Verified

**CUAD definition:** Can a party terminate this contract without cause (solely by giving a notice and allowing a waiting period to expire)?

**Model's quote:**
> This Agreement shall remain in full force and effect until revoked by any party hereto in a signed writing provided to each other party hereto, and then only with respect to such revoking party.

**Model's reason:** Allows any party to terminate without cause by written notice.

**Second review (confirm):** Allows any party to terminate unilaterally by written notice, fitting termination for convenience.

**CUAD's marked text for this type** (0 spans):
> (none)

**Surrounding contract text:**
> …he information concerning the other persons making the filing, unless such person knows or has reason to believe that such information is inaccurate. »This Agreement shall remain in full force and effect until revoked by any party hereto in a signed writing provided to each other party hereto, and then only with respect to such revoking party.« This Agreement may be executed in any number of counterparts all of which taken together shall constitute one and the same instrument.
> IN WITNESS WH…

**Your label:** ______  **Note:** ______

### Case 3: Termination for Convenience, PcquoteComInc_19990721_S-1A_EX-10.11_6377149_EX-10.11_Co-Branding Agreement1

**Status shown:** Verified

**CUAD definition:** Can a party terminate this contract without cause (solely by giving a notice and allowing a waiting period to expire)?

**Model's quote:**
> Notice expressing a desire to terminate this Agreement will be sent by certified mail to the address indicated above. Said termination will be effective as of the last day of the month in which this anniversary occurs.

**Model's reason:** Allows termination without cause by giving notice.

**Second review (confirm):** Provides unilateral notice-based termination without cause, fitting termination for convenience.

**CUAD's marked text for this type** (0 spans):
> (none)

**Surrounding contract text:**
> …cified on the signature page of this Agreement. Neither PCQ nor ABW shall terminate or alter this Agreement except as stated herein.
>  B. \[\*\*\*\] »Notice expressing a desire to terminate this Agreement will be sent by certified mail to the address indicated above. Said termination will be effective as of the last day of the month in which this anniversary occurs.« C. Notwithstanding the provisions of (A), and (B) above, should a party to this Agreement be in material breach of the Agreement, the other par…

**Your label:** ______  **Note:** ______

### Case 4: Termination for Convenience, TRIZETTOGROUPINC_08_18_1999-EX-10.17-TECHNICAL INFRASTRUCTURE MAINTENANCE AGREEMENT

**Status shown:** Verified

**CUAD definition:** Can a party terminate this contract without cause (solely by giving a notice and allowing a waiting period to expire)?

**Model's quote:**
> Customer, upon thirty days prior written notice, may cancel this Agreement at the end of the Initial Term and thereafter on each anniversary of the end of the Initial Term.

**Model's reason:** Provides a party the right to terminate without cause by giving notice.

**Second review (confirm):** It grants the customer unilateral termination with notice, fitting termination for convenience.

**CUAD's marked text for this type** (0 spans):
> (none)

**Surrounding contract text:**
> …pment. Swap equipment is subject to availability. Customer is to incur the cost of travel time/expenses of MMMW Personal.
>  (d) »Customer, upon thirty days prior written notice, may cancel this Agreement at the end of the Initial Term and thereafter on each anniversary of the end of the Initial Term.« MMMW may cancel this Agreement if the Customer does not remit payment according to the terms of MMMW's invoice.
>  (e) The term…

**Your label:** ______  **Note:** ______

---

## B. Verified finding with no CUAD match (CUAD marks this type elsewhere)

### Case 5: Anti-Assignment, BerkshireHillsBancorpInc_20120809_10-Q_EX-10.16_7708169_EX-10.16_Endorsement Agreement

**Status shown:** Verified

**CUAD definition:** Is consent or notice required of a party if the contract is assigned to a third party?

**Model's quote:**
> The License Rights are exclusive to Berkshire and may not be assigned or in any way conveyed by Berkshire without Auriemma's express written consent, except in the event of a merger by Berkshire with another entity offering Banking Services.

**Model's reason:** Specifies consent required for assignment, with exception for merger.

**Second review (confirm):** The clause requires Auriemma's written consent for Berkshire to assign the license rights, establishing an anti-assignment restriction.

**CUAD's marked text for this type** (1 span):
> Berkshire may not assign this Agreement, in whole or in part, without Auriemma's written consent.

**Surrounding contract text:**
> …riod and throughout the Contract Territory solely in connection with the advertisement and promotion of Berkshire and the Financial Services; c) »The License Rights are exclusive to Berkshire and may not be assigned or in any way conveyed by Berkshire without Auriemma's express written consent, except in the event of a merger by Berkshire with another entity offering Banking Services.« Source: BERKSHIRE HILLS BANCORP INC, 10-Q, 8/9/2012
>  3. EXCLUSIVITY. Auriemma expressly agrees and undertakes that: a) The right to use…

**Your label:** ______  **Note:** ______

---

## C. Failed quote (not found word for word)

### Case 6: Cap on Liability, GSITECHNOLOGYINC_11_16_2009-EX-10.2-INTELLECTUAL PROPERTY AGREEMENT between SONY ELECTRONICS INC. and GSI TECHNOLOGY, INC.

**Status shown:** Needs review

**CUAD definition:** Does the contract include a cap on liability upon the breach of a party's obligation? This includes time limitation for the counterparty to bring claims or maximum amount for recovery. This includes monetary caps, exclusions of types of damages such as consequential or indirect damages, and time limits on bringing claims.

**Model's quote:**
> NEITHER PARTY SHALL HAVE ANY LIABILITY WHATSOEVER TO THE OTHER PARTY OR ANY OTHER PERSON FOR OR ON ACCOUNT OF ANY INJURY, LOSS, OR DAMAGE, OF ANY KIND OR NATURE SUSTAINED BY, OR ANY DAMAGE ASSESSED OR ASSERTED AGAINST, OR ANY OTHER LIABILITY INCURRED BY OR IMPOSED UPON THE OTHER PARTY OR ANY OTHER PERSON, ARISING OUT OF OR IN CONNECTION WITH OR RESULTING FROM (A) THE PRODUCTION, USE, SALE, OFFER FOR SALE, OTHER DISPOSITIONS OR IMPORTATION OF ANY APPARATUS OR PRODUCT MADE BY THAT PARTY; OR (B) ANY ADVERTISING OR OTHER PROMOTIONAL ACTIVITIES MADE BY THAT PARTY WITH RESPECT TO ANY OF THE FOREGOING, AND EACH PARTY SHALL HOLD THE OTHER PARTY, AND ITS AFFILIATES, OFFICERS, AGENTS, OR EMPLOYEES, HARMLESS IN THE EVENT IT, OR ITS OFFICERS, AGENTS, OR EMPLOYEES, IS HELD LIABLE.

**Model's reason:** Limits liability to the extent of no liability whatsoever, acting as a liability cap.

**Closest contract passage** (word similarity 0.996):
> NEITHER PARTY SHALL HAVE ANY LIABILITY WHATSOEVER TO THE 12
>  OTHER PARTY OR ANY OTHER PERSON FOR OR ON ACCOUNT OF ANY INJURY, LOSS, OR DAMAGE, OF ANY KIND OR NATURE SUSTAINED BY, OR ANY DAMAGE ASSESSED OR ASSERTED AGAINST, OR ANY OTHER LIABILITY INCURRED BY OR IMPOSED UPON THE OTHER PARTY OR ANY OTHER PERSON, ARISING OUT OF OR IN CONNECTION WITH OR RESULTING FROM (A) THE PRODUCTION, USE, SALE, OFFER FOR SALE, OTHER DISPOSITIONS OR IMPORTATION OF ANY APPARATUS OR PRODUCT MADE BY THAT PARTY; OR (B) ANY ADVERTISING OR OTHER PROMOTIONAL ACTIVITIES MADE BY THAT PARTY WITH RESPECT TO ANY OF THE FOREGOING, AND EACH PARTY SHALL HOLD THE OTHER PARTY, AND ITS AFFILIATES, OFFICERS, AGENTS, OR EMPLOYEES, HARMLESS IN THE EVENT IT, OR ITS OFFICERS, AGENTS, OR EMPLOYEES, IS HELD LIABLE.

**What differs (model's quote → contract):**

- insert: “” → “12”

**Closest passage overlaps CUAD's marked text for this type:** no

**CUAD's marked text for this type** (0 spans):
> (none)

**Surrounding contract text:**
> …8.14 Disclaimer NOTHING IN THIS IP AGREEMENT SHALL BE DEEMED TO BE A REPRESENTATION OR WARRANTY BY EITHER PARTY OF THE VALIDITY OF ANY PATENT. »NEITHER PARTY SHALL HAVE ANY LIABILITY WHATSOEVER TO THE 12
>  OTHER PARTY OR ANY OTHER PERSON FOR OR ON ACCOUNT OF ANY INJURY, LOSS, OR DAMAGE, OF ANY KIND OR NATURE SUSTAINED BY, OR ANY DAMAGE ASSESSED OR ASSERTED AGAINST, OR ANY OTHER LIABILITY INCURRED BY OR IMPOSED UPON THE OTHER PARTY OR ANY OTHER PERSON, ARISING OUT OF OR IN CONNECTION WITH OR RESULTING FROM (A) THE PRODUCTION, USE, SALE, OFFER FOR SALE, OTHER DISPOSITIONS OR IMPORTATION OF ANY APPARATUS OR PRODUCT MADE BY THAT PARTY; OR (B) ANY ADVERTISING OR OTHER PROMOTIONAL ACTIVITIES MADE BY THAT PARTY WITH RESPECT TO ANY OF THE FOREGOING, AND EACH PARTY SHALL HOLD THE OTHER PARTY, AND ITS AFFILIATES, OFFICERS, AGENTS, OR EMPLOYEES, HARMLESS IN THE EVENT IT, OR ITS OFFICERS, AGENTS, OR EMPLOYEES, IS HELD LIABLE.« THIS SECTION 8 IS NOT INTENDED TO NEGATE OR SUPERSEDE ANY REPRESENTATION OR WARRANTY EXPRESSLY MADE BY SONY IN THIS IP AGREEMENT. 9. Miscellaneo…

**Your label:** ______  **Note:** ______

### Case 7: Anti-Assignment, GSITECHNOLOGYINC_11_16_2009-EX-10.2-INTELLECTUAL PROPERTY AGREEMENT between SONY ELECTRONICS INC. and GSI TECHNOLOGY, INC.

**Status shown:** Needs review

**CUAD definition:** Is consent or notice required of a party if the contract is assigned to a third party?

**Model's quote:**
> This IP Agreement will be binding upon and inure to the benefit of the Parties hereto and their respective successors and permitted assigns, but will not be assignable or delegable by any Party without the prior written consent of the other Party. Notwithstanding the foregoing, a Party may transfer or assign its rights under this IP Agreement in connection with a merger, acquisition or sale of all or substantially all of its assets, on condition that it provides the other Party with notice of the transfer or assignment. Any attempted transfer in contravention of this Section 9.3 shall be null and void.

**Model's reason:** Requires consent or notice for assignment, limiting assignability.

**Closest contract passage** (word similarity 0.995):
> This IP Agreement will be binding upon and inure to the benefit of the Parties hereto and their respective successors and permitted assigns, but will not be assignable or delegable by any Party without the prior written consent of the other Party. Notwithstanding the foregoing, a Party may transfer or assign its rights under this IP Agreement in connection with a merger, acquisition or sale of all or substantially all of its assets, on condition that it provides the 14
>  other Party with notice of the transfer or assignment. Any attempted transfer in contravention of this Section 9.3 shall be null and void.

**What differs (model's quote → contract):**

- insert: “” → “14”

**Closest passage overlaps CUAD's marked text for this type:** yes

**CUAD's marked text for this type** (2 spans):
> This IP Agreement will be binding upon and inure to the benefit of the Parties hereto and their respective successors and permitted assigns, but will not be assignable or delegable by any Party without the prior written consent of the other Party.
> 
> (next span)
> 
> Any attempted transfer in contravention of this Section 9.3 shall be null and void.

**Surrounding contract text:**
> …ident to this IP Agreement, and in preparing to consummate and consummating the transactions provided for herein. 9.3 Successors and Assigns »This IP Agreement will be binding upon and inure to the benefit of the Parties hereto and their respective successors and permitted assigns, but will not be assignable or delegable by any Party without the prior written consent of the other Party. Notwithstanding the foregoing, a Party may transfer or assign its rights under this IP Agreement in connection with a merger, acquisition or sale of all or substantially all of its assets, on condition that it provides the 14
>  other Party with notice of the transfer or assignment. Any attempted transfer in contravention of this Section 9.3 shall be null and void.« 9.4 Waiver No action taken pursuant to this IP Agreement will be deemed to constitute a waiver of compliance with any representations, warra…

**Your label:** ______  **Note:** ______

### Case 8: Governing Law, PRIMEENERGYRESOURCESCORP_04_02_2007-EX-10.28-COMPLETION AND LIQUIDITY MAINTENANCE AGREEMENT

**Status shown:** Needs review

**CUAD definition:** Which state/country's law governs the interpretation of the contract?

**Model's quote:**
> This Agreement shad be deemed a contract made under and shall be construed in accordance with and governed by the laws ofthe State of Texas and that actions arising out ofthis Agreement may be litigated in courts having situs in Harris County, Texas.

**Model's reason:** Specifies the governing law as Texas.

**Closest contract passage** (word similarity 0.965):
> This Agreement shad be deemed a contract made under and shall be construed in accordance with and governed by the laws ofthe State ofTexas and that actions arising out ofthis Agreement may be litigated in courts having situs in Harris County, Texas.

**What differs (model's quote → contract):**

- replace: “of Texas” → “ofTexas”

**Closest passage overlaps CUAD's marked text for this type:** yes

**CUAD's marked text for this type** (1 span):
> This Agreement shad be deemed a contract made under and shall be construed in accordance with and governed by the laws ofthe State ofTexas and that actions arising out ofthis Agreement may be litigated in courts having situs in Harris County, Texas.

**Surrounding contract text:**
> …. Offshore is executing this Agreement to acknowledge that a breach ofthis Agreement would result in an Event ofDefault under the Credit Agreement. »This Agreement shad be deemed a contract made under and shall be construed in accordance with and governed by the laws ofthe State ofTexas and that actions arising out ofthis Agreement may be litigated in courts having situs in Harris County, Texas.« This agreement is executed the date first hereinafter written,
> PRIMEEVERGY CORPORATION By:-\*" Beverly A. Cummings\_\_\_\_\_\_ Beverly A. Cummings Execut…

**Your label:** ______  **Note:** ______

### Case 9: Termination for Convenience, TUNIUCORP_03_06_2014-EX-10-COOPERATION AGREEMENT

**Status shown:** Needs review

**CUAD definition:** Can a party terminate this contract without cause (solely by giving a notice and allowing a waiting period to expire)?

**Model's quote:**
> Party B shall have the right to terminate this Agreement in advance without the prior written consent from Party A, by sending a written notice to Party A but Party A may not terminate or rescind this Agreement;

**Model's reason:** Allows Party B to end the contract unilaterally without cause.

**Closest contract passage** (word similarity 0.96):
> Party B shall have the right to terminate this Agreement in advance without the prior written consent from Party A, bysending a written notice to Party A but Party A may not terminate or rescind this Agreement;

**What differs (model's quote → contract):**

- replace: “by sending” → “bysending”

**Closest passage overlaps CUAD's marked text for this type:** yes

**CUAD's marked text for this type** (1 span):
> Party B shall have the right to terminate this Agreement in advance without the prior written consent from Party A, bysending a written notice to Party A but Party A may not terminate or rescind this Agreement;

**Surrounding contract text:**
> …Prior to the expiration of the Term of Cooperation , this Agreement shall only be terminated upon occurrence of the followingcircumstances:
>  6.1.1 »Party B shall have the right to terminate this Agreement in advance without the prior written consent from Party A, bysending a written notice to Party A but Party A may not terminate or rescind this Agreement;« 6.1.2 One Party requests to terminate this Agreement when the other Party is declared bankrupt in accordance with the laws;
>  6.1.3 Party B fails…

**Your label:** ______  **Note:** ______

---

## D. Not found: check, but CUAD marks this clause

### Case 10: Change of Control, BerkshireHillsBancorpInc_20120809_10-Q_EX-10.16_7708169_EX-10.16_Endorsement Agreement

**Status shown:** Not found: check

**CUAD definition:** Does one party have the right to terminate or is consent or notice required of the counterparty if such party undergoes a change of control, such as a merger, stock sale, transfer of all or substantially all of its assets or business, or assignment by operation of law?

**Model's quote:** none (no finding of this type in this contract)

**CUAD's marked text for this type** (1 span):
> In the case of reorganization, merger, consolidation, or sale of all or substantially all of its assets, any attempt to assign this Agreement other than as permitted above will be null and void.

**Surrounding contract text:**
> …ligations) of this Agreement, as he may so desire. Berkshire may not assign this Agreement, in whole or in part, without Auriemma's written consent. »In the case of reorganization, merger, consolidation, or sale of all or substantially all of its assets, any attempt to assign this Agreement other than as permitted above will be null and void.« 23. SIGNIFICANCE OF HEADINGS. Paragraph headings contained in this Agreement are solely for the purpose of aiding speedy location of subject…

**Your label:** ______  **Note:** ______

### Case 11: Change of Control, GSITECHNOLOGYINC_11_16_2009-EX-10.2-INTELLECTUAL PROPERTY AGREEMENT between SONY ELECTRONICS INC. and GSI TECHNOLOGY, INC.

**Status shown:** Not found: check

**CUAD definition:** Does one party have the right to terminate or is consent or notice required of the counterparty if such party undergoes a change of control, such as a merger, stock sale, transfer of all or substantially all of its assets or business, or assignment by operation of law?

**Model's quote:** none (no finding of this type in this contract)

**CUAD's marked text for this type** (2 spans):
> Notwithstanding the foregoing, a Party may transfer or assign its rights under this IP Agreement in connection with a merger, acquisition or sale of all or substantially all of its assets, on condition that it provides the
> 
> (next span)
> 
> other Party with notice of the transfer or assignment.

**Surrounding contract text:**
> …pective successors and permitted assigns, but will not be assignable or delegable by any Party without the prior written consent of the other Party. »Notwithstanding the foregoing, a Party may transfer or assign its rights under this IP Agreement in connection with a merger, acquisition or sale of all or substantially all of its assets, on condition that it provides the« 14
>  other Party with notice of the transfer or assignment. Any attempted transfer in contravention of this Section 9.3 shall be null an…

**Your label:** ______  **Note:** ______

### Case 12: Cap on Liability, HPILHOLDING_01_07_2015-EX-99.1-COOPERATION AGREEMENT

**Status shown:** Not found: check

**CUAD definition:** Does the contract include a cap on liability upon the breach of a party's obligation? This includes time limitation for the counterparty to bring claims or maximum amount for recovery. This includes monetary caps, exclusions of types of damages such as consequential or indirect damages, and time limits on bringing claims.

**Model's quote:** none (no finding of this type in this contract)

**CUAD's marked text for this type** (2 spans):
> GINARES agrees that the sole and exclusive remedy for money damages related to this Agreement and the transactions contemplated hereby shall be the rights to indemnification set forth in this Section 9.
> 
> (next span)
> 
> HPIL ET agrees that the sole and exclusive remedy for money damages relating to this Agreement and the transactions contemplated hereby shall be the rights to indemnification set forth in this Section 10.

**Surrounding contract text:**
> …observed by HPIL ET under this Agreement or any of the other agreements or instruments executed and delivered by HPIL ET on the Closing Date. 9.2. »GINARES agrees that the sole and exclusive remedy for money damages related to this Agreement and the transactions contemplated hereby shall be the rights to indemnification set forth in this Section 9.« 10. HPIL ET's Indemnity 10.1. GINARES shall indemnify, defend, and hold harmless HPIL ET from, against and with respect to any claim, liability,…

**Your label:** ______  **Note:** ______

### Case 13: Cap on Liability, TUNIUCORP_03_06_2014-EX-10-COOPERATION AGREEMENT

**Status shown:** Not found: check

**CUAD definition:** Does the contract include a cap on liability upon the breach of a party's obligation? This includes time limitation for the counterparty to bring claims or maximum amount for recovery. This includes monetary caps, exclusions of types of damages such as consequential or indirect damages, and time limits on bringing claims.

**Model's quote:** none (no finding of this type in this contract)

**CUAD's marked text for this type** (2 spans):
> Notwithstanding the foregoing provisions, neither Party shall be responsible to the other Party in respect of any indirect loss or damage caused hereunder.
> 
> (next span)
> 
> The demand for liquidated damages and specific performance in respect of any breach during the Term of Cooperation are all remedies that the non-breaching Party shall have under this Agreement.

**Surrounding contract text:**
> …g to this Agreement and applicable laws. If both Parties breach this Agreement, they shall each assume their own liabilities for breach respectively. »Notwithstanding the foregoing provisions, neither Party shall be responsible to the other Party in respect of any indirect loss or damage caused hereunder.« 8.2 The demand for liquidated damages and specific performance in respect of any breach during the Term of Cooperation are all remedies that the n…

**Your label:** ______  **Note:** ______

---

## E. Cap on Liability span missed in a contract Verified for Cap

### Case 14: Cap on Liability, CYBERIANOUTPOSTINC_07_09_1998-EX-10.13-PROMOTION AGREEMENT

**Status shown:** Verified

**CUAD definition:** Does the contract include a cap on liability upon the breach of a party's obligation? This includes time limitation for the counterparty to bring claims or maximum amount for recovery. This includes monetary caps, exclusions of types of damages such as consequential or indirect damages, and time limits on bringing claims.

**Model's Verified Cap on Liability quote in this contract (for reference):**
> NEITHER PARTY WILL BE LIABLE FOR ANY SPECIAL, INDIRECT, CONSEQUENTIAL OR INCIDENTAL DAMAGES ARISING OUT OF OR RELATED TO THIS AGREEMENT, HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY (INCLUDING NEGLIGENCE), AND EVEN IF SUCH PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

**Model's quote for this span:** none

**CUAD's marked text for this type** (1 span):
> CNET shall indemnify and hold the Company harmless from and against any costs, losses, liabilities and expenses, including all court costs, reasonable expenses and reasonable attorney's fees (collectively, "Losses") that the Company may suffer, incur or be subjected to by reason of any legal action, proceeding, arbitration or other claim by a third party, whether commenced or threatened, arising out of or as a result of (a) any breach or alleged breach by CNET of its representations, warranties or covenants hereunder; or (b) the operation of the CNET Sites (except in cases where the Company is required to indemnify CNET under the following paragraph), including claims of infringement or misappropriation of intellectual property rights.

**Surrounding contract text:**
> …extent (if any) contained within Promotions delivered to CNET by the Company.
> 8. Mutual Indemnification.
>  8.1 Indemnification by CNET. »CNET shall indemnify and hold the Company harmless from and against any costs, losses, liabilities and expenses, including all court costs, reasonable expenses and reasonable attorney's fees (collectively, "Losses") that the Company may suffer, incur or be subjected to by reason of any legal action, proceeding, arbitration or other claim by a third party, whether commenced or threatened, arising out of or as a result of (a) any breach or alleged breach by CNET of its representations, warranties or covenants hereunder; or (b) the operation of the CNET Sites (except in cases where the Company is required to indemnify CNET under the following paragraph), including claims of infringement or misappropriation of intellectual property rights.« 8.2 Indemnification by the Company. The Company shall indemnify and hold CNET harmless from and against any Losses that CNET may suf…

**Your label:** ______  **Note:** ______

### Case 15: Cap on Liability, TRIZETTOGROUPINC_08_18_1999-EX-10.17-TECHNICAL INFRASTRUCTURE MAINTENANCE AGREEMENT

**Status shown:** Verified

**CUAD definition:** Does the contract include a cap on liability upon the breach of a party's obligation? This includes time limitation for the counterparty to bring claims or maximum amount for recovery. This includes monetary caps, exclusions of types of damages such as consequential or indirect damages, and time limits on bringing claims.

**Model's Verified Cap on Liability quote in this contract (for reference):**
> MMMW's entire liability and the Customer's sole and exclusive remedy for claims related to or arising out of this Agreement for any cause and regardless of the form of action, whether in contract or tort, including negligence and strict liability, shall be the remedies set forth in Section 8, provided that if MMMW fails after repeated attempts to perform those remedies, MMMW's entire liability shall be the Customer's actual, direct damages such as would be provided in a court of law, not to exceed the charge for service for the item that caused the damages.

**Model's quote for this span:** none

**CUAD's marked text for this type** (1 span):
> MMMW's sole and exclusive obligation under this warranty shall be at its option to repair or exchange any hardware not in satisfactory operating condition.

**Surrounding contract text:**
> …bject to MMMW's inspection and acceptance of the hardware for service; and
>  2) subject to normal use and conditions. »MMMW's sole and exclusive obligation under this warranty shall be at its option to repair or exchange any hardware not in satisfactory operating condition.« Said obligation shall be subject to the conditions and charges of Section 3, 4 and 5 and the prompt submission of…

**Your label:** ______  **Note:** ______

### Case 16: Cap on Liability, CYBERIANOUTPOSTINC_07_09_1998-EX-10.13-PROMOTION AGREEMENT

**Status shown:** Verified

**CUAD definition:** Does the contract include a cap on liability upon the breach of a party's obligation? This includes time limitation for the counterparty to bring claims or maximum amount for recovery. This includes monetary caps, exclusions of types of damages such as consequential or indirect damages, and time limits on bringing claims.

**Model's Verified Cap on Liability quote in this contract (for reference):**
> NEITHER PARTY WILL BE LIABLE FOR ANY SPECIAL, INDIRECT, CONSEQUENTIAL OR INCIDENTAL DAMAGES ARISING OUT OF OR RELATED TO THIS AGREEMENT, HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY (INCLUDING NEGLIGENCE), AND EVEN IF SUCH PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

**Model's quote for this span:** none

**CUAD's marked text for this type** (1 span):
> The Company shall indemnify and hold CNET harmless from and against any Losses that CNET may suffer, incur or be subjected to by reason of any legal action, proceeding,
>  arbitration or other claim by a third party, whether commenced or threatened, arising out of or as a result of (a) any breach or alleged breach by the Company of its representations, warranties or covenants hereunder; (b) the use by CNET of the Company Marks or any content provided by the Company to CNET expressly for display in connection with or as part of the Promotions, including claims of infringement or misappropriation of intellectual property rights; or (c) the operation of the Company Site or the offer or sale of the Products by the Company or through the Company Sit

**Surrounding contract text:**
> …aragraph), including claims of infringement or misappropriation of intellectual property rights.
>  8.2 Indemnification by the Company. »The Company shall indemnify and hold CNET harmless from and against any Losses that CNET may suffer, incur or be subjected to by reason of any legal action, proceeding,
>  arbitration or other claim by a third party, whether commenced or threatened, arising out of or as a result of (a) any breach or alleged breach by the Company of its representations, warranties or covenants hereunder; (b) the use by CNET of the Company Marks or any content provided by the Company to CNET expressly for display in connection with or as part of the Promotions, including claims of infringement or misappropriation of intellectual property rights; or (c) the operation of the Company Site or the offer or sale of the Products by the Company or through the Company Sit« e.
>  8.3 Indemnification Procedures. If any party entitled to indemnification under this section (an "Indemnified Party") makes an inde…

**Your label:** ______  **Note:** ______
