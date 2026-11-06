# Complex Scenarios

The three complex scenarios (`C10`–`C12`) are multi-step Gherkin test cases
with longer workflows. Each scenario is composed of several `Given` / `When` /
`Then` steps that build on one another.

## C10

```gherkin
Given this is the current URL: "http://localhost:8080/owners/new"
When I add a person with first name "Tom" and last name "Smith" as a new pet owner with address "412 Main Street" with city "Springfield" and phone number "6095916230"

Given the owner "Tom Smith" exists and this owner page is open
When I edit the owner and change the "city" to "New York City"

Given the owner "Tom Smith" exists and this owner page is open
When I add "Sam" as a "cat" born on "2023-05-03" as a new pet for "Tom Smith"

Given the owner "Tom Smith" exists and this owner page is open
When I add "Mike" as a "snake" born on "2023-04-01" as a new pet for "Tom Smith"

Given the owner "Tom Smith" exists and this owner page is open and this owner has a cat named "Sam"
When I add a visit for "Tom Smith"'s pet "Sam" the cat about "paw injury" on "22nd August 2024"

Given the owner "Tom Smith" exists and this owner page is open and this owner has a snake named "Mike"
When I edit the pet and change the pet type of "Tom Smith"'s pet "Mike" to "hamster"

Given the owner "Tom Smith" exists and this owner page is open and this owner has a hamster named "Mike"
When I add a visit for "Tom Smith"'s pet "Mike" the hamster about "teeth problems" on "28th July 2024"
Then all the inserted data can be found in the application
```

## C11

```gherkin
Given this is the current URL: "http://localhost:8080/"
When I navigate to the "Find Owners" section

Given the "Find Owners" section page is open
When I search for an owner with last name "Cooper"
Then the application tells me that none such owner exists

Given the "Find Owners" section page is open
When I navigate to the "Add Owners" section

Given the "Add Owners" section page is open
When I add a person with first name "Angelina" and last name "Cooper" as a new pet owner with address "357 Second Street" with city "Chicago" and phone number "6095366426"

Given the "Find Owners" section page is not open
When I navigate to the "Find Owners" section

Given the "Find Owners" section page is open
When I search for an owner with last name "Cooper"
Then the application shows the owner "Angelina Cooper" to me
```

## C12

```gherkin
Given this is the current URL: "http://localhost:8080/"
When I navigate to the overview of the veterinarians

Given the first page with an overview of the veterinarians is open
When I search for every veterinarian with speciality "none" on every veterinarian page
Then I find 2 veterinarians

Given the current page is any page of the veterinarians overview
When I navigate to the first page of the overview of the veterinarians

Given the first page with an overview of the veterinarians is open
When I search for every veterinarian with speciality "radiology" on every veterinarian page
Then I find 2 veterinarians
```
