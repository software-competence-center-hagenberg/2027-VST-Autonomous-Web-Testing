# Simple Scenarios

The nine simple scenarios (`S1`–`S9`) are single-step or short,
straightforward Gherkin test cases for the PetClinic application. Each is
written in the standard `Given` / `When` / `Then` form.

## S1

```gherkin
Given this is the current URL: "http://localhost:8080/owners/find"
When I search for an owner with the last name "Franklin"
Then "George Franklin" can be seen as an owner
```

## S2

```gherkin
Given this is the current URL: "http://localhost:8080/owners/new"
When I add a person with first name "John" and last name "Smith" as a new pet owner
Then "John Smith" is an owner
```

## S3

```gherkin
Given this is the current URL: "http://localhost:8080/owners/2/pets/new"
When I add "Jamie" as a "cat" born on "2023-05-12" as a new pet for the existing owner "Betty Davis"
Then "Betty Davis" has a cat named "Jamie"
```

## S4

```gherkin
Given this is the current URL: "http://localhost:8080/owners/4/edit"
When I change the "address" of "Harold Davis" to "123 Main Street" and the "city" to "Springfield"
Then the new "address" of "Harold Davis" is "123 Main Street" in the new city "Springfield"
```

## S5

```gherkin
Given this is the current URL: "http://localhost:8080/owners/6/edit"
When I change the "telephone number" of "Jean Coleman" to "6095556643"
Then the new "telephone number" of "Jean Coleman" is "6095556643"
```

## S6

```gherkin
Given this is the current URL: "http://localhost:8080/owners/7/pets/9/edit"
When I change the pet type of "Jeff Black"s existing pet "Lucky" to "cat"
Then the pet named "Lucky" is a "cat"
```

## S7

```gherkin
Given this is the current URL: "http://localhost:8080/vets.html"
When I search for the speciality of the veterinarian "Helen Leary"
Then I find the speciality "radiology" for "Helen Leary"
```

## S8

```gherkin
Given this is the current URL: "http://localhost:8080/vets.html"
When I check the specialities of the veterinarians for a "dentist"
Then I find the veterinarian "Linda Douglas" with speciality containing "dentist"
```

## S9

```gherkin
Given this is the current URL: "http://localhost:8080/owners/3/pets/3/visits/new"
When I add a visit for the pet "Rosy" of the existing owner "Eduardo Rodriquez" on "23rd May 2024" about "paw injury"
Then the pet "Rosy" has an appointment about "paw injury" on "23rd May 2024"
```
