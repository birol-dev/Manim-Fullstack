"use strict";

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const header = document.querySelector(".site-header");
const navToggle = document.querySelector(".nav-toggle");
const navMenu = document.querySelector("#nav-menu");

function setHeaderState() {
  if (!header) return;
  header.classList.toggle("is-scrolled", window.scrollY > 18);
}

setHeaderState();
window.addEventListener("scroll", setHeaderState, { passive: true });

if (navToggle && navMenu) {
  navToggle.addEventListener("click", () => {
    const isOpen = navToggle.getAttribute("aria-expanded") === "true";
    navToggle.setAttribute("aria-expanded", String(!isOpen));
    navToggle.setAttribute("aria-label", isOpen ? "Open navigation menu" : "Close navigation menu");
    navMenu.classList.toggle("is-open", !isOpen);
    document.body.classList.toggle("nav-open", !isOpen);
  });

  navMenu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      navToggle.setAttribute("aria-expanded", "false");
      navToggle.setAttribute("aria-label", "Open navigation menu");
      navMenu.classList.remove("is-open");
      document.body.classList.remove("nav-open");
    });
  });
}

document.querySelectorAll(".faq-trigger").forEach((trigger) => {
  trigger.addEventListener("click", () => {
    const item = trigger.closest(".faq-item");
    if (!item) return;

    const willOpen = !item.classList.contains("is-open");
    document.querySelectorAll(".faq-item").forEach((faq) => {
      faq.classList.remove("is-open");
      const faqButton = faq.querySelector(".faq-trigger");
      faqButton?.setAttribute("aria-expanded", "false");
    });

    item.classList.toggle("is-open", willOpen);
    trigger.setAttribute("aria-expanded", String(willOpen));
  });
});

const revealTargets = document.querySelectorAll(
  ".pain-card, .workflow-board article, .feature-row, .table-row, .timeline article, .audience-grid article, .quote-panel, .faq-item"
);

if (prefersReducedMotion) {
  revealTargets.forEach((target) => target.classList.add("is-visible"));
} else if ("IntersectionObserver" in window) {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      });
    },
    { threshold: 0.12, rootMargin: "0px 0px -80px 0px" }
  );

  revealTargets.forEach((target, index) => {
    target.classList.add("reveal");
    target.style.transitionDelay = `${Math.min(index * 28, 220)}ms`;
    revealObserver.observe(target);
  });
} else {
  revealTargets.forEach((target) => target.classList.add("is-visible"));
}

const canvas = document.querySelector("#equation-field");
const context = canvas?.getContext("2d");

let canvasWidth = 0;
let canvasHeight = 0;

function resizeCanvas() {
  if (!canvas || !context) return;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const rect = canvas.getBoundingClientRect();
  canvasWidth = rect.width;
  canvasHeight = rect.height;
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
}

const glyphs = [
  "∫",
  "∂",
  "π",
  "λ",
  "∑",
  "θ",
  "∇",
  "lim",
  "sin",
  "cos",
  "e^{iπ}",
  "MathTex",
  "Scene",
  "Write",
  "Transform",
];

let particles = [];
let animationFrame = 0;

function seedParticles() {
  if (!canvas) return;
  const count = Math.max(34, Math.min(80, Math.floor(canvasWidth / 22)));

  particles = Array.from({ length: count }, (_, index) => ({
    x: Math.random() * canvasWidth,
    y: Math.random() * canvasHeight,
    speed: 0.14 + Math.random() * 0.34,
    size: 13 + Math.random() * 18,
    alpha: 0.08 + Math.random() * 0.22,
    glyph: glyphs[index % glyphs.length],
    hue: index % 3,
  }));
}

function drawEquationField() {
  if (!canvas || !context) return;

  context.clearRect(0, 0, canvasWidth, canvasHeight);

  particles.forEach((particle) => {
    particle.y -= particle.speed;
    particle.x += Math.sin((particle.y + particle.size) / 90) * 0.12;

    if (particle.y < -40) {
      particle.y = canvasHeight + 40;
      particle.x = Math.random() * canvasWidth;
    }

    const color = particle.hue === 0 ? "240, 184, 77" : particle.hue === 1 ? "45, 167, 162" : "217, 107, 60";
    context.font = `${particle.size}px "JetBrains Mono", monospace`;
    context.fillStyle = `rgba(${color}, ${particle.alpha})`;
    context.fillText(particle.glyph, particle.x, particle.y);
  });

  if (!prefersReducedMotion) {
    animationFrame = window.requestAnimationFrame(drawEquationField);
  }
}

if (canvas && context) {
  resizeCanvas();
  seedParticles();
  drawEquationField();

  window.addEventListener(
    "resize",
    () => {
      resizeCanvas();
      seedParticles();
      drawEquationField();
    },
    { passive: true }
  );

  if (document.fonts) {
    document.fonts.ready.then(() => {
      drawEquationField();
    });
  }
}

/* --- Scene Interactivity --- */
const scenes = {
  eulers: {
    title: "workspace / eulers_identity.py",
    status: "Rendering 78%",
    code: `<span class="code-keyword">from</span> manim <span class="code-keyword">import</span> *

<span class="code-keyword">class</span> <span class="code-class">EulersIdentity</span>(Scene):
    <span class="code-keyword">def</span> <span class="code-fn">construct</span>(self):
        eq = MathTex(
            <span class="code-string">r"e^{i\\pi}+1=0"</span>,
            font_size=<span class="code-num">92</span>
        )
        box = SurroundingRectangle(eq)
        self.play(Write(eq))
        self.play(Create(box))`,
    preview: `<span>e<sup>iπ</sup> + 1 = 0</span>`,
    logs: `<p><span>stdout</span> Building EulersIdentity</p>
<p><span>progress</span> Animation 3 of 4</p>
<p><span>file</span> media/videos/1080p60.mp4</p>`
  },
  vector: {
    title: "workspace / vector_field.py",
    status: "Rendering 45%",
    code: `<span class="code-keyword">from</span> manim <span class="code-keyword">import</span> *

<span class="code-keyword">class</span> <span class="code-class">VectorField</span>(Scene):
    <span class="code-keyword">def</span> <span class="code-fn">construct</span>(self):
        func = <span class="code-keyword">lambda</span> p: np.sin(p[<span class="code-num">0</span>]/<span class="code-num">2</span>)*UR + np.cos(p[<span class="code-num">1</span>]/<span class="code-num">2</span>)*LEFT
        vf = ArrowVectorField(func)
        self.play(Create(vf))`,
    preview: `<span style="font-size: 1.5rem; text-align: center; line-height: 1.4;">F(x,y) = sin(x/2)î + cos(y/2)ĵ<br><span style="font-size: 1rem; opacity: 0.6; display: block; margin-top: 10px;">[Vector Field Arrows]</span></span>`,
    logs: `<p><span>stdout</span> Building VectorField</p>
<p><span>progress</span> Animation 1 of 2</p>
<p><span>file</span> media/videos/vector_field.mp4</p>`
  },
  fourier: {
    title: "workspace / fourier_trace.py",
    status: "Rendering 60%",
    code: `<span class="code-keyword">from</span> manim <span class="code-keyword">import</span> *

<span class="code-keyword">class</span> <span class="code-class">FourierTrace</span>(Scene):
    <span class="code-keyword">def</span> <span class="code-fn">construct</span>(self):
        path = Circle(radius=<span class="code-num">2</span>)
        fourier = FourierSeries(path, n_vectors=<span class="code-num">8</span>)
        self.play(Create(fourier))`,
    preview: `<span style="font-size: 1.8rem;">∑ c<sub>n</sub> e<sup>i n ω t</sup></span>`,
    logs: `<p><span>stdout</span> Building FourierTrace</p>
<p><span>progress</span> Animation 2 of 3</p>
<p><span>file</span> media/videos/fourier_trace.mp4</p>`
  }
};

const sceneButtons = document.querySelectorAll("[data-scene]");
const appTitle = document.querySelector("#app-title");
const renderStatus = document.querySelector("#render-status");
const codeContent = document.querySelector("#code-content");
const canvasPreview = document.querySelector("#canvas-preview");
const logStream = document.querySelector("#log-stream");

sceneButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const sceneKey = btn.getAttribute("data-scene");
    const sceneData = scenes[sceneKey];
    if (!sceneData) return;

    sceneButtons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");

    if (appTitle) appTitle.textContent = sceneData.title;
    if (renderStatus) renderStatus.textContent = sceneData.status;
    if (codeContent) codeContent.innerHTML = sceneData.code;
    if (canvasPreview) canvasPreview.innerHTML = sceneData.preview;
    if (logStream) logStream.innerHTML = sceneData.logs;
  });
});

/* --- Scroll Spy Navigation --- */
const sections = document.querySelectorAll("section[id]");
const navLinks = document.querySelectorAll(".nav-menu a");

function scrollSpy() {
  const scrollPosition = window.scrollY + 120; // account for header offset

  sections.forEach((section) => {
    const sectionTop = section.offsetTop;
    const sectionHeight = section.offsetHeight;
    const sectionId = section.getAttribute("id");

    if (scrollPosition >= sectionTop && scrollPosition < sectionTop + sectionHeight) {
      navLinks.forEach((link) => {
        link.classList.remove("active");
        if (link.getAttribute("href") === `#${sectionId}`) {
          link.classList.add("active");
        }
      });
    }
  });
}

window.addEventListener("scroll", scrollSpy, { passive: true });
scrollSpy();

