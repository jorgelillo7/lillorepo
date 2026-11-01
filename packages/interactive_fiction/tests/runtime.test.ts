import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";
import { Runtime, type Action } from "../src/engine/runtime.ts";
import { parseTwee, type Story } from "../src/engine/source.ts";

const mini = parseTwee(readFileSync(new URL("./fixtures/mini.twee", import.meta.url), "utf8"));

function story(passages: Record<string, string>, start = "Start"): Story {
  return {
    title: "t",
    start,
    format: "Harlowe",
    formatVersion: "3.3.9",
    stylesheet: "",
    passages: Object.entries(passages).map(([name, text]) => ({ name, tags: [], text })),
  };
}

function show(passages: Record<string, string>) {
  const rt = new Runtime(story(passages));
  const vars = rt.start();
  return { ...rt.visit(vars, "Start"), vars, rt };
}

describe("markup", () => {
  test("a newline is a line break, but not inside a collapsed block", () => {
    expect(show({ Start: "a\nb{\n c \n  d\n}" }).html).toBe("a<br>bc d");
  });

  test("a collapsed block keeps the line breaks of what it displays or prints, as Harlowe does", () => {
    const html = show({ Start: '{\nx (display:"B") (print:"p1\np2")\ny\n}', B: "b1\nb2" }).html;
    expect(html).toBe("x b1<br>b2 p1<br>p2 y");
  });

  test("bold, italic and raw HTML pass through", () => {
    expect(show({ Start: "''b'' //i// <span class=\"x\">s</span>" }).html).toBe(
      '<b>b</b> <i>i</i> <span class="x">s</span>',
    );
  });

  test("a bare variable prints escaped, inside raw HTML too", () => {
    expect(show({ Start: '(set:$c to "<A>")<h3>$c</h3>' }).html).toBe("<h3>&lt;A&gt;</h3>");
  });

  test("text-colour wraps its hook in the Harlowe colour", () => {
    expect(show({ Start: "(text-colour:navy)[G]" }).html).toBe('<tw-hook style="color:#1919e6">G</tw-hook>');
  });
});

describe("state", () => {
  test("startup passages run once before the first passage", () => {
    const rt = new Runtime(mini);
    expect(rt.start()).toMatchObject({ keys: 0, bag: [], code: "" });
  });

  test("`it` is the current value of the variable being set", () => {
    expect(show({ Start: "(set:$n to 1)(set:$n to it + 2)$n" }).html).toBe("3");
  });

  test("arrays concatenate with + and filter with find", () => {
    const { vars } = show({
      Start: '(set:$a to (a:"x","y") + (a:"z"))(set:$b to (find: _i where _i is not "y", ...$a))',
    });
    expect(vars.b).toEqual(["x", "z"]);
  });

  test("else and else-if follow the previous condition among siblings", () => {
    const src = "(set:$k to 2)(if:$k is 1)[one](else-if:$k is 2)[two](else:)[other]";
    expect(show({ Start: src }).html).toBe("two");
  });

  test("cond returns the first true branch, and a code hook renders as markup", () => {
    expect(show({ Start: "(cond: false, [no], true, [''yes''])" }).html).toBe("<b>yes</b>");
  });

  test("using an unset variable fails loudly instead of printing nothing", () => {
    expect(() => show({ Start: "$missing" })).toThrow(/not set/);
  });
});

describe("links and navigation", () => {
  test("print re-parses a string, so link arrays become clickable", () => {
    const r = show({ Start: "(set:$r to (a:'[[Go|B]]'))(for:each _o, ...$r)[(print:_o)]", B: "" });
    expect(r.actions).toEqual([{ kind: "link", label: "Go", target: "B" }]);
    expect(r.html).toContain('data-action="0"');
  });

  test("goto stops the passage and shows its target, keeping what was set before it", () => {
    const r = show({ Start: '(set:$x to 1)(goto:"B")never', B: "B$x" });
    expect(r.passage).toBe("B");
    expect(r.html).toBe("B1");
  });

  test("a (link:) runs its hook on click, and a goto inside it navigates", () => {
    const r = show({ Start: '(link:"Take")[(set:$t to true)(goto:"B")]', B: "" });
    const action = r.actions[0] as Extract<Action, { kind: "reveal" }>;
    const out = r.rt.reveal(r.vars, action);
    expect(out.goto).toBe("B");
    expect(r.vars.t).toBe(true);
  });

  test("display renders another passage inline with the same state", () => {
    expect(show({ Start: "(set:$n to 5)(display:\"P\")", P: "n=$n" }).html).toBe("n=5");
  });

  test("a header passage is rendered above every passage", () => {
    const rt = new Runtime(mini);
    const vars = rt.start();
    vars.keys = 2;
    expect(rt.visit(vars, "Door").html.startsWith('<div id="hud">Keys: 2</div>')).toBe(true);
  });

  test("an input is bound to its variable and shows its current value", () => {
    const r = show({ Start: '(set:$c to "KEY")(input: bind $c)' });
    expect(r.inputs).toEqual(["c"]);
    expect(r.html).toContain('data-bind="c" value="KEY"');
  });
});
