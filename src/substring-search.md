---
title: Substring Search
toc: false
sql:
  posts: ./data/vrgarchive.parquet
---

# Substring Search

This uses plain substring search on the post comments and plots number of matching posts per month.
To search for multiple terms, separate them with a comma.

This is sort of slow (though still impressively fast for running in your browser), and afaik
there's no way to get a progress bar, but it should eventually finish.

If you want to actually see the matching posts, try the [full text search](full-text-search).

```js
function debounce(input, delay = 500) {
  return Generators.observe(notify => {
    let timer = null;
    let value;

    // On input, check if we recently reported a value.
    // If we did, do nothing and wait for a delay;
    // otherwise, report the current value and set a timeout.
    function inputted() {
      if (timer !== null) return;
      notify(value = input.value);
      timer = setTimeout(delayed, delay);
    }

    // After a delay, check if the last-reported value is the current value.
    // If it’s not, report the new value.
    function delayed() {
      timer = null;
      if (value === input.value) return;
      notify(value = input.value);
    }

    input.addEventListener("input", inputted), inputted();
    return () => input.removeEventListener("input", inputted);
  });
}

const input_text = Inputs.text({
    label: "substring search",
    placeholder: "search for something",
    value: "sneed, feed, seed"
  });

const pattern_term = debounce(input_text);

display(input_text);
```

```sql id=pattern_over_time
WITH search_terms AS (
    -- Split the comma-separated list into rows, trim whitespace, and lowercase
    SELECT lower(trim(unnest(string_split(${pattern_term}, ',')))) AS term
)
SELECT
    cast(date_trunc('month', epoch_ms(p.timestamp * 1000)) as timestamp) AS themonth,
    st.term as term, -- Include the specific term found
    count(*) as num_comments -- Count occurrences for that specific term in that month
FROM
    posts p
CROSS JOIN -- Check every post against every search term
    search_terms st
WHERE
    p.comment IS NOT NULL -- Avoid errors with contains on NULL
    AND contains(lower(p.comment), st.term) -- Case-insensitive check against the term
GROUP BY
    themonth,
    st.term -- Group by month AND by term
```

```js
Plot.plot({
  color: {legend: true},
  width: width,
  x: { interval: "month"},
  marks: [
    Plot.lineY(pattern_over_time, {curve: "step", "x": "themonth", stroke: "term", y: "num_comments", tip: 'x' })
  ]
})
```
