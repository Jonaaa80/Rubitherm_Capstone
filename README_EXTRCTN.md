## Field extracted
* customer first name
* customer last name
* customer role
* customer email
* customer phone
* company name
* company website
* company address
* tags
* extracted by
* message 

## Core Logic 
1. We are reading the email from the very bottom to the stopper (first "Von:" from the bottom) and this will be the block we extract information
2. If there's "Contry:" "Phone:" "Company:" "Name:" "Email:", then we pass to the 'form_inquiry_extractor' function.
3. It not, then we pass to the 'direct_email_extractor' function.
4. We will find a signature block and we will extract information 


## Form_inquiry_extractor
1. We find a block with 'Name:' ~ 'Country:' and extract information 
2. We extract information are only in the website inquiry format
    "first_name": "Matthias",
    "last_name": "Moser",
    "company": "Moser Konstruktion GmbH &",
    "customer_phone": "0491721442009",
    "email": "m.moser@moser-konstruktion.de",
    "address": "Deutschland", 
    "message": "..."
    "tag": 
3. Information not included are
    "roles": list(set(roles)),
    "website": list(set(websites)),

## Direct_email_extractor 
1. We extract the name, email address, company name from the "Von:" line.
    a: what's inside of "<>" will be considered the email address.
    b: string after "@" will be considered the company name. However, the generic email addresses and rubitherm will be ignored
    c: if the company name is not extracted then we extract from the signature block and find 'gmbh', 'ltd' using Regex

2. From the signature block, the customer_phone, customer role, website address will be extracted by Regex. The company address will be extracted by SpaCy GPE,LOC
3. if the company address is not extracted from the step 2, then we will find a entire line with +8 character, ',', +1 number for the company address
