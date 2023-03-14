"use strict";

const resultList = document.querySelector(".results");
const cid = document.getElementById("commit_id");
const headline = document.getElementById("headline");

async function getResultsData() {
	const response = await fetch("/api/data");
	const data = await response.json();
	return data;
}

/* sample data
{
	"commit_id": "1234567890",
	"results": [{
		"type": "error" | "fail",
		"test_name": "test_app",
		"reasons": ["ImportError - Failed to import test module test_pass",
					"Traceback (most recent call last) - File \"/Example_CI/clone_runner/tests/test_pass.py\", line 3, in <module> - import app",
					"ModuleNotFoundError - No module named 'app'"]
	},
	{...}]
}
*/

class Result {
	constructor(result) {
		this.type = result.type;
		this.test_name = result.test_name;
		this.reasons = result.reasons;
	}
}

class Results {
	constructor(data) {
		this.commit_id = data.commit_id;
		this.res = data.results.map(result => new Result(result));
	}
}

const popluateHeadline = (results) => {
	let errors = 0;
	let fails = 0;
	results.res.reduce((_, curr) => {
		curr.type === "error" ? errors++ : fails++;
	}, 0);

	if (!errors && !fails) {
		headline.textContent = "All tests passed";
		headline.classList.add("passed");
	} else {
		headline.innerHTML = `We found `;
		if (errors) {
			headline.innerHTML += `<span class="error">${errors} errors</span>`
			if (errors === 1) {
				const sp = headline.querySelector(".error");
				sp.textContent = sp.textContent.substring(0, sp.textContent.length - 1);
			}
		}

		if (fails) {
			if (errors) {
				headline.innerHTML += " and ";
			}
			headline.innerHTML += `<span class="fail">${fails} failures</span>`
			if (fails === 1) {
				const sp = headline.querySelector(".fail");
				sp.textContent = sp.textContent.substring(0, sp.textContent.length - 1);
			}
		}
	}
}

const populatePage = (results) => {
	cid.textContent = results.commit_id;
	popluateHeadline(results);
	// clear it
	resultList.textContent = "";
	results.res.map(result => {
		const li = document.createElement("li");
		let reasons = "";
		result.reasons.map(reason => {
			reasons += reason + "\n";
		});
		li.textContent = `${result.test_name} - ${reasons}`;
		console.log(li.textContent);
		// li.classList.add(result.type);
		resultList.appendChild(li);
	});
}

const app = async () => {
	const testdata = await getResultsData();
	console.log(testdata);
	const results = new Results(testdata);
	console.log(results);
	populatePage(results);
}

app();


