# Negative Scenarios

The three negative scenarios (`N13`–`N15`) are designed so that the expected
behavior is for the agent to **stop and report failure** rather than complete
the task. In each case the requested action is invalid or impossible, so a
correct run must not alter the test inputs to force a success.

## N13

```gherkin
Given this is the current url: "http://localhost:8080/owners/find"
When I click on the "Filter" button next to the search bar
Then I see five options to filter owners
```

## N14

```gherkin
Given this is the current url: "http://localhost:8080/owners/1/pets/new"
When I add "Simba" as a "lion" born on "2023-05-12" as a new pet for the existing owner "George Franklin"
Then "George Franklin" has a lion named "Simba"
```

## N15

```gherkin
Given this is the current URL: "http://localhost:8080/owners/new"
When I add a person with first name "Jackie" and last name "Chan" as a new pet owner with address "345 Jack Street" with city "Springfield" and phone number "7266/61936"
Then "Jackie Chan" is added as an owner
```
